"""Gold layer: business-ready data products (star schema + a mart).

This is where data from three systems that never talked to each other
is joined into one view the business asked for:
"Which permitted sites are highest risk, and who operates them?"
"""
import duckdb

from .config import LAKE, ROOT

GOLD_SQL = {
    "dim_customer": """
        SELECT row_number() OVER (ORDER BY customer_id) AS customer_key,
               customer_id, full_name, email, town, created_date
        FROM silver_crm_customers
    """,
    "dim_site": """
        SELECT row_number() OVER (ORDER BY s.site_id)   AS site_key,
               s.site_id, s.site_name, s.site_type, s.latitude, s.longitude,
               s.customer_id                            AS operator_customer_id
        FROM silver_permits_sites s
    """,
    "dim_date": """
        SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key, CAST(d AS DATE) AS date,
               year(d) AS year, quarter(d) AS quarter, month(d) AS month,
               CASE WHEN month(d) >= 4 THEN year(d) ELSE year(d) - 1 END AS financial_year  -- UK FY starts April
        FROM range(DATE '2018-01-01', DATE '2031-01-01', INTERVAL 1 DAY) t(d)
    """,
    "fact_inspection": """
        SELECT i.inspection_id,
               ds.site_key,
               CAST(strftime(i.inspected_on, '%Y%m%d') AS INTEGER) AS date_key,
               i.inspector_team, i.outcome,
               i.finding_count, i.high_severity_findings,
               CASE i.outcome WHEN 'Major breach' THEN 1 ELSE 0 END AS is_major_breach
        FROM silver_inspections_inspections i
        LEFT JOIN gold_dim_site ds ON ds.site_id = i.site_id
    """,
    "mart_site_risk": """
        WITH last12 AS (
            SELECT site_key,
                   CAST(count(*) AS INTEGER)                    AS inspections_12m,
                   CAST(sum(is_major_breach) AS INTEGER)        AS major_breaches_12m,
                   CAST(sum(high_severity_findings) AS INTEGER) AS high_findings_12m
            FROM gold_fact_inspection f
            JOIN gold_dim_date d USING (date_key)
            WHERE d.date >= current_date - INTERVAL 12 MONTH
            GROUP BY site_key
        ), active_permits AS (
            SELECT site_id, count(*) AS active_permits, sum(annual_fee_gbp) AS annual_fees_gbp
            FROM silver_permits_permits WHERE status = 'Active' GROUP BY site_id
        )
        SELECT s.site_id, s.site_name, s.site_type,
               c.full_name AS operator_name, c.town AS operator_town,
               coalesce(p.active_permits, 0)     AS active_permits,
               coalesce(p.annual_fees_gbp, 0)    AS annual_fees_gbp,
               coalesce(l.inspections_12m, 0)    AS inspections_12m,
               coalesce(l.major_breaches_12m, 0) AS major_breaches_12m,
               coalesce(l.high_findings_12m, 0)  AS high_findings_12m,
               -- simple, explainable score agreed with the business (see README)
               coalesce(l.major_breaches_12m, 0) * 5 + coalesce(l.high_findings_12m, 0) * 2
                 + CASE WHEN coalesce(l.inspections_12m, 0) = 0 THEN 3 ELSE 0 END AS risk_score
        FROM gold_dim_site s
        LEFT JOIN gold_dim_customer c ON c.customer_id = s.operator_customer_id
        LEFT JOIN active_permits p    ON p.site_id = s.site_id
        LEFT JOIN last12 l            ON l.site_key = s.site_key
        ORDER BY risk_score DESC, s.site_id
    """,
}


def build(con: duckdb.DuckDBPyConnection) -> list[dict]:
    results = []
    for name, sql in GOLD_SQL.items():  # dict order = dependency order
        out = LAKE / "gold" / name / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY ({sql}) TO '{out.as_posix()}' (FORMAT parquet)")
        con.execute(f"CREATE OR REPLACE VIEW gold_{name} AS SELECT * FROM '{out.as_posix()}'")
        rows = con.execute(f"SELECT count(*) FROM gold_{name}").fetchone()[0]
        results.append({"layer": "gold", "dataset": name, "rows_out": rows, "path": str(out.relative_to(ROOT))})
    return results
