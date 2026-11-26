// Common Data Platform - core Azure resources.
// Deploy:  az deployment group create -g rg-cdp-dev -f infra/main.bicep -p infra/dev.bicepparam
// Design notes: docs/adr/0001-lakehouse-medallion.md, docs/adr/0003-security-and-identity.md

targetScope = 'resourceGroup'

@description('Short environment name, used in resource names.')
@allowed(['dev', 'test', 'prod'])
param env string = 'dev'

@description('Azure region.')
param location string = resourceGroup().location

@description('Short workload name, used in resource names.')
@maxLength(6)
param workload string = 'cdp'

@description('Deploy Microsoft Purview for catalog and lineage (has a running cost, off by default in dev).')
param deployPurview bool = false

@description('Object id of the Entra ID group for platform engineers.')
param engineersGroupObjectId string

var suffix = uniqueString(resourceGroup().id)
var tags = {
  workload: workload
  environment: env
  owner: 'data-architecture'
  costCentre: 'data-platform'
  dataClassification: 'official'
}
var lakeContainers = ['landing', 'bronze', 'silver', 'gold', 'quarantine']

// ---------- Monitoring ----------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${workload}-${env}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------- Data lake (ADLS Gen2) ----------
resource lake 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${workload}${env}${take(suffix, 6)}'
  location: location
  tags: tags
  sku: { name: env == 'prod' ? 'Standard_ZRS' : 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true                 // hierarchical namespace = ADLS Gen2
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false        // identity-based access only
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: env == 'prod' ? 'Disabled' : 'Enabled'
  }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: lake
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 14 }
    containerDeleteRetentionPolicy: { enabled: true, days: 14 }
  }
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for c in lakeContainers: {
  parent: blobSvc
  name: c
  properties: { publicAccess: 'None' }
}]

// Move old bronze batches to cool storage to save cost (raw data is kept for audit/replay).
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: lake
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'bronze-to-cool'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['bronze/'] }
            actions: { baseBlob: { tierToCool: { daysAfterModificationGreaterThan: 30 } } }
          }
        }
      ]
    }
  }
}

// ---------- Secrets ----------
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${workload}-${env}-${take(suffix, 6)}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
  }
}

// ---------- Orchestration (Azure Data Factory) ----------
resource adf 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: 'adf-${workload}-${env}-${take(suffix, 6)}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Transformation (Azure Databricks) ----------
resource dbw 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: 'dbw-${workload}-${env}'
  location: location
  tags: tags
  sku: { name: 'premium' }            // premium needed for Unity Catalog
  properties: {
    managedResourceGroupId: subscriptionResourceId('Microsoft.Resources/resourceGroups', 'rg-${workload}-${env}-dbw-managed')
  }
}

// ---------- Governance (Microsoft Purview, optional) ----------
resource purview 'Microsoft.Purview/accounts@2021-12-01' = if (deployPurview) {
  name: 'pview-${workload}-${env}-${take(suffix, 6)}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// ---------- Access (RBAC, least privilege) ----------
var roles = {
  blobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  blobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  kvSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource adfLakeWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: lake
  name: guid(lake.id, adf.id, roles.blobDataContributor)
  properties: {
    principalId: adf.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
  }
}

resource adfKvReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, adf.id, roles.kvSecretsUser)
  properties: {
    principalId: adf.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.kvSecretsUser)
  }
}

resource engineersLake 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: lake
  name: guid(lake.id, engineersGroupObjectId, roles.blobDataContributor)
  properties: {
    principalId: engineersGroupObjectId
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
  }
}

resource purviewLakeReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployPurview) {
  scope: lake
  name: guid(lake.id, 'purview', roles.blobDataReader)
  properties: {
    principalId: deployPurview ? purview!.identity.principalId : ''
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataReader)
  }
}

// ---------- Diagnostics ----------
resource adfDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: adf
  name: 'to-log-analytics'
  properties: {
    workspaceId: logs.id
    logs: [
      { category: 'PipelineRuns', enabled: true }
      { category: 'ActivityRuns', enabled: true }
    ]
  }
}

output lakeName string = lake.name
output dataFactoryName string = adf.name
output databricksUrl string = dbw.properties.workspaceUrl
output keyVaultName string = kv.name
