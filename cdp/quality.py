"""Data quality rules, kept as data so data owners can read and agree them.

Each rule is a SQL condition that must be TRUE for a good row.
Rows that fail any 'error' rule go to quarantine with the reason, they are
never silently dropped. 'warn' rules are only counted and reported.
"""
from pathlib import Path

import duckdb

from .config import LAKE, ROOT

RULES = {
    "crm.customers": [
        ("customer_id_present", "error", "customer_id IS NOT NULL"),
        ("email_valid", "warn", "regexp_full_match(email, '[^@\\s]+@[^@\\s]+\\.[a-z]{2,}')"),
    ],
    "permits.sites": [
        ("site_id_present", "error", "site_id IS NOT NULL"),
        ("coords_in_england", "error", "latitude BETWEEN 49.8 AND 55.9 AND longitude BETWEEN -6.5 AND 2.0"),
    ],
    "permits.permits": [
        ("permit_id_present", "error", "permit_id IS NOT NULL"),
        ("expiry_after_issue", "error", "expiry_date > issued_date"),
        ("status_known", "error", "status IN ('Active','Suspended','Expired')"),
    ],
    "inspections.inspections": [
        ("site_ref_present", "error", "site_id IS NOT NULL"),
        ("not_in_future", "error", "inspected_on <= current_date"),
        ("outcome_known", "error", "outcome IN ('Compliant','Minor breach','Major breach')"),
    ],
}


def apply_rules(con: duckdb.DuckDBPyConnection, dataset: str, staged_view: str) -> tuple[str, list[dict]]:
    """Split staged_view into <view>_good and a quarantine parquet file. Returns good view name + metrics."""
    rules = RULES.get(dataset, [])
    errors = [r for r in rules if r[1] == "error"]
    total = con.execute(f"SELECT count(*) FROM {staged_view}").fetchone()[0]
    metrics = []
    for name, level, cond in rules:
        failed = con.execute(f"SELECT count(*) FROM {staged_view} WHERE NOT coalesce({cond}, false)").fetchone()[0]
        metrics.append({"dataset": dataset, "rule": name, "level": level, "rows_checked": total,
                        "rows_failed": failed, "pass_rate": round(1 - failed / total, 4) if total else 1.0})

    reason_sql = " , ".join(f"CASE WHEN NOT coalesce({c}, false) THEN '{n}' END" for n, _, c in errors) or "NULL"
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW {staged_view}_checked AS
        SELECT *, concat_ws(',', {reason_sql}) AS _dq_failed_rules FROM {staged_view}
    """)
    q_path: Path = LAKE / "quarantine" / dataset.replace(".", "/") / "data.parquet"
    q_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM {staged_view}_checked WHERE _dq_failed_rules <> '') "
                f"TO '{q_path.as_posix()}' (FORMAT parquet)")
    con.execute(f"""CREATE OR REPLACE TEMP VIEW {staged_view}_good AS
                    SELECT * EXCLUDE (_dq_failed_rules) FROM {staged_view}_checked WHERE _dq_failed_rules = ''""")
    q_rows = con.execute(f"SELECT count(*) FROM '{q_path.as_posix()}'").fetchone()[0]
    metrics.append({"dataset": dataset, "rule": "_quarantined_total", "level": "error", "rows_checked": total,
                    "rows_failed": q_rows, "pass_rate": round(1 - q_rows / total, 4) if total else 1.0,
                    "quarantine_path": str(q_path.relative_to(ROOT))})
    return f"{staged_view}_good", metrics
