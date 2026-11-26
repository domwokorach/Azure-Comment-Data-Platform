"""Silver layer: cleaned, typed, de-duplicated, conformed data.

One row per business key, standard column names (snake_case),
standard types (DATE, DECIMAL), and quality rules applied.
"""
import duckdb

from .config import LAKE, ROOT, Source
from .quality import apply_rules

# Typing and conforming SQL per dataset. {src} = all bronze batches for that entity.
STAGING_SQL = {
    "crm.customers": """
        SELECT customer_id,
               trim(full_name)                         AS full_name,
               lower(trim(email))                      AS email,
               town,
               try_cast(created_date AS DATE)          AS created_date,
               try_cast(updated_at AS TIMESTAMP)       AS updated_at,
               _batch_id, _ingested_at
        FROM {src}
        QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY try_cast(updated_at AS TIMESTAMP) DESC) = 1
    """,
    "permits.sites": """
        SELECT site_id,
               operator_customer_id                    AS customer_id,
               site_name, site_type,
               try_cast(latitude AS DOUBLE)            AS latitude,
               try_cast(longitude AS DOUBLE)           AS longitude,
               _batch_id, _ingested_at
        FROM {src}
        QUALIFY row_number() OVER (PARTITION BY site_id ORDER BY _ingested_at DESC) = 1
    """,
    "permits.permits": """
        SELECT permit_id, site_id, permit_type, status,
               try_cast(issued_date AS DATE)           AS issued_date,
               try_cast(expiry_date AS DATE)           AS expiry_date,
               try_cast(annual_fee_gbp AS DECIMAL(10,2)) AS annual_fee_gbp,
               _batch_id, _ingested_at
        FROM {src}
        QUALIFY row_number() OVER (PARTITION BY permit_id ORDER BY _ingested_at DESC) = 1
    """,
    # Semi-structured JSON: flatten the nested inspector struct, keep findings
    # as a list but also derive simple columns analysts actually use.
    "inspections.inspections": """
        SELECT inspection_id,
               site_ref                                AS site_id,
               try_cast(inspected_on AS DATE)          AS inspected_on,
               inspector.id                            AS inspector_id,
               inspector.team                          AS inspector_team,
               outcome,
               len(findings)                           AS finding_count,
               len(list_filter(findings, f -> f.severity = 'high')) AS high_severity_findings,
               findings,
               nullif(notes, '')                       AS notes,
               _batch_id, _ingested_at
        FROM {src}
        QUALIFY row_number() OVER (PARTITION BY inspection_id ORDER BY _ingested_at DESC) = 1
    """,
}


def build(con: duckdb.DuckDBPyConnection, src: Source) -> tuple[dict, list[dict]]:
    bronze_glob = (LAKE / "bronze" / src.source_system / src.entity / "*" / "data.parquet").as_posix()
    if src.load_type == "full":
        # full loads: only the latest batch is the truth
        src_sql = (f"(SELECT * FROM read_parquet('{bronze_glob}') WHERE _batch_id = "
                   f"(SELECT max(_batch_id) FROM read_parquet('{bronze_glob}')))")
    else:
        # incremental loads: union all batches, newest version of each key wins
        src_sql = f"read_parquet('{bronze_glob}')"

    view = f"stg_{src.source_system}_{src.entity}"
    con.execute(f"CREATE OR REPLACE TEMP VIEW {view} AS {STAGING_SQL[src.name].format(src=src_sql)}")
    good, dq = apply_rules(con, src.name, view)

    out = LAKE / "silver" / src.source_system / src.entity / "data.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM {good}) TO '{out.as_posix()}' (FORMAT parquet)")
    con.execute(f"CREATE OR REPLACE VIEW silver_{src.source_system}_{src.entity} AS SELECT * FROM '{out.as_posix()}'")
    rows = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]
    return {"layer": "silver", "dataset": src.name, "rows_out": rows, "path": str(out.relative_to(ROOT))}, dq
