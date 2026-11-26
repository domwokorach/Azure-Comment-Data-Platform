# ADR-0001: Use a lakehouse with bronze, silver and gold layers

**Status:** Accepted · **Date:** 2026-11-26

## Context
The Agency has data in separate systems (CRM, permitting, field inspections). Each team makes its own copies and reports, numbers do not match, and joining data across systems takes days of manual work. We need one common platform that can take structured, semi-structured and unstructured data and serve both BI and future data services.

## Options considered
| Option | Good | Bad |
|---|---|---|
| A. Traditional data warehouse only (Azure SQL / Synapse dedicated pool) | Familiar, strong SQL | Poor fit for JSON and files, cost grows with storage, schema needed up front |
| B. Data lake only (files, no structure) | Cheap, flexible | Turns into a "data swamp", hard to trust, no clear contracts |
| **C. Lakehouse with medallion layers (ADLS Gen2 + Delta + Databricks)** | Cheap storage, handles any format, clear quality stages, open formats | Needs standards and discipline, team must learn Spark/Delta |
| D. Microsoft Fabric | All-in-one SaaS, simple for BI teams | Newer, capacity pricing harder to predict, less control |

## Decision
Option C. Bronze keeps raw data for audit and replay, silver is the trusted cleaned layer, gold holds business data products. Delta Lake gives ACID tables and time travel on cheap storage.

## Consequences
- We must publish and enforce standards (see `docs/standards/ingestion-standards.md`).
- The design maps cleanly to Fabric (OneLake also uses Delta), so moving later is a lift, not a rebuild.
- A local DuckDB version of the same design lets engineers test logic without cloud cost.
