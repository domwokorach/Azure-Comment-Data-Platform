using './main.bicep'

param env = 'dev'
param workload = 'cdp'
param deployPurview = false
param engineersGroupObjectId = '00000000-0000-0000-0000-000000000000' // replace with your Entra ID group
