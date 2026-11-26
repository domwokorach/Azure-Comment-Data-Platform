"""Tests run the full pipeline once on the sample data and check the contract of each layer."""
import duckdb
import pytest

from cdp.config import LAKE
from cdp.pipeline import run


@pytest.fixture(scope="module")
def report():
    return run(clean=True)


@pytest.fixture(scope="module")
def con(report):
    return duckdb.connect()


def q(con, sql):
    return con.execute(sql).fetchone()[0]


def p(*parts):
    return (LAKE.joinpath(*parts) / "data.parquet").as_posix()


def test_bronze_keeps_every_source_row(report):
    bronze = {s["dataset"]: s["rows_out"] for s in report["steps"] if s["layer"] == "bronze"}
    assert bronze["crm.customers"] == 210          # includes the 10 CRM history duplicates
    assert bronze["inspections.inspections"] == 1500


def test_silver_has_one_row_per_business_key(con, report):
    for path, key in [(p("silver", "crm", "customers"), "customer_id"),
                      (p("silver", "permits", "permits"), "permit_id"),
                      (p("silver", "inspections", "inspections"), "inspection_id")]:
        assert q(con, f"SELECT count(*) - count(DISTINCT {key}) FROM '{path}'") == 0


def test_no_row_is_lost_bad_rows_are_quarantined(con, report):
    good = q(con, f"SELECT count(*) FROM '{p('silver', 'inspections', 'inspections')}'")
    bad = q(con, f"SELECT count(*) FROM '{p('quarantine', 'inspections', 'inspections')}'")
    assert good + bad == 1500
    assert bad > 0
    assert q(con, f"SELECT count(*) FROM '{p('quarantine', 'inspections', 'inspections')}' "
                  f"WHERE _dq_failed_rules = ''") == 0


def test_silver_types_and_formats(con, report):
    assert q(con, f"SELECT count(*) FROM '{p('silver', 'crm', 'customers')}' WHERE email <> lower(trim(email))") == 0
    assert q(con, f"SELECT max(inspected_on) <= current_date FROM '{p('silver', 'inspections', 'inspections')}'")


def test_gold_fact_joins_to_dimensions(con, report):
    orphans = q(con, f"SELECT count(*) FROM '{p('gold', 'fact_inspection')}' f "
                     f"LEFT JOIN '{p('gold', 'dim_site')}' d USING (site_key) WHERE d.site_key IS NULL")
    assert orphans == 0


def test_risk_mart_covers_every_site(con, report):
    assert q(con, f"SELECT count(*) FROM '{p('gold', 'mart_site_risk')}'") == 300
    assert q(con, f"SELECT min(risk_score) >= 0 FROM '{p('gold', 'mart_site_risk')}'")


def test_run_report_records_lineage_and_owners(report):
    assert {s["owner"] for s in report["sources"]} >= {"Customer Services", "Permitting Team", "Field Operations"}
    assert all("path" in s for s in report["steps"])
    assert any(m["rule"] == "_quarantined_total" for m in report["data_quality"])
