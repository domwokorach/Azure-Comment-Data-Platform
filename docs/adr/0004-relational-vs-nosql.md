# ADR-0004: Where relational and NoSQL stores fit

**Status:** Accepted · **Date:** 2026-11-26

## Context
Teams ask whether new services should use Azure SQL or Cosmos DB, and whether the lakehouse replaces both.

## Decision
| Need | Store | Why |
|---|---|---|
| Analytics, history, joining many systems | Lakehouse (Delta on ADLS) | Cheap at scale, any format, batch and BI friendly |
| Control tables, reference data, transactional apps with strong relationships | Azure SQL Database | ACID, foreign keys, mature tooling |
| Operational apps needing low-latency reads of flexible documents (for example a mobile inspections app) | Azure Cosmos DB | Schema-flexible JSON, global scale, millisecond reads |
| Serving gold data to apps via API | Azure SQL or Cosmos DB fed from gold | Lakehouse is not built for many small, fast lookups |

## Consequences
The lakehouse is the **analytical** source of truth, not every app's database. Operational stores feed the platform (via landing) and can be fed from gold where an app needs curated data.
