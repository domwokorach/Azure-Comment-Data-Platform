# ADR-0003: Identity-based access only, no keys or passwords in pipelines

**Status:** Accepted · **Date:** 2026-11-26

## Context
The platform will hold personal data (customer contact details). Storage account keys and connection strings in pipelines are a common cause of data leaks and are hard to rotate.

## Decision
- Storage account shared-key access is **disabled**. Every service uses **Managed Identity** with Entra ID RBAC.
- Data Factory gets *Storage Blob Data Contributor* on the lake, and *Key Vault Secrets User* for the few source systems that still need a password.
- People get access through **Entra ID groups**, never as individuals.
- Production storage has public network access disabled (private endpoints).

## Consequences
- No secrets to rotate in pipeline code. Access is auditable in one place.
- Developers need the right group membership before they can work, so onboarding needs a short checklist.
