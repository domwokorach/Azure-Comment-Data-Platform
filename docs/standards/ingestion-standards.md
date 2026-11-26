# Data Ingestion Standards

**Status:** Approved (v1.0) · **Owner:** Data Architecture · **Applies to:** every dataset loaded into the Common Data Platform

These are the rules every team follows when they bring data onto the platform. They exist so that data from any system arrives in the same predictable way, can be trusted, and can be found.

## 1. Register before you load
- Every source must have an entry in the **source registry** (`config/sources.json` locally, `ctl.source_registry` in Azure SQL).
- The entry must name a **business owner**, a **data classification** (`public`, `internal`, `personal`, `sensitive`), the **primary key**, and the **load type** (`full` or `incremental`).
- No registry entry, no load. This is what keeps the catalog complete.

## 2. Layers and what each one promises

| Layer | Purpose | Who can read | Promise |
|---|---|---|---|
| `landing` | Files as dropped by source systems | Platform only | None. Temporary, cleared after 30 days |
| `bronze` | Raw copy + audit columns, append only | Platform engineers | Exactly what the source sent. Never edited |
| `silver` | Cleaned, typed, one row per key | Engineers, analysts | Quality rules passed, standard names and types |
| `gold` | Business data products (star schemas, marts) | Business users, BI, APIs | Documented, owned, stable contract |
| `quarantine` | Rows that failed quality rules | Engineers, data owners | Kept with the reason it failed |

## 3. Bronze rules
- Store in Parquet (Delta in Azure). Path: `bronze/<source_system>/<entity>/batch_id=<yyyyMMddTHHmmss>/`.
- Add these columns and nothing else: `_source_system`, `_source_file`, `_batch_id`, `_ingested_at`.
- CSV is read as text. Do not cast types in bronze, so a bad value never stops the load.
- Semi-structured data (JSON, XML) is stored with its nested structure kept.

## 4. Silver rules
- Column names in `snake_case`. Dates as `DATE`, money as `DECIMAL(10,2)`, timestamps in UTC.
- Exactly one row per primary key. For history rows, the latest `updated_at` wins.
- Quality rules are written down as data (`cdp/quality.py`), agreed with the data owner.
  - `error` rule fails → the row goes to quarantine with the rule name.
  - `warn` rule fails → the row is kept and the failure is counted in the run report.
- Rows are never silently dropped: `silver + quarantine = bronze` (after de-duplication).

## 5. Gold rules
- Modelled for the question being answered: star schema (facts + conformed dimensions) for BI, marts for specific use cases.
- Each gold dataset has an owner, a description and a refresh schedule in the catalog.
- Personal data only appears in gold when there is a documented purpose (UK GDPR Article 5).

## 6. Naming
| Thing | Pattern | Example |
|---|---|---|
| Azure resource | `<type>-<workload>-<env>` | `adf-cdp-prod` |
| Lake folder | `<layer>/<source_system>/<entity>` | `silver/permits/sites` |
| Gold table | `dim_*`, `fact_*`, `mart_*` | `mart_site_risk` |
| Audit columns | leading underscore | `_batch_id` |

## 7. Every run produces evidence
Each pipeline run writes a **run report** (`data/lake/_runs/<batch_id>.json`) with rows in and out per step, quality results and dataset owners. In Azure this goes to Log Analytics and lineage goes to Purview.
