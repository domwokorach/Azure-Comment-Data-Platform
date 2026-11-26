"""Run the whole platform end to end and write a run report (audit + lineage)."""
import json
import shutil
from datetime import datetime, timezone

import duckdb

from . import bronze, gold, silver
from .config import LAKE, ROOT, load_sources


def run(clean: bool = False) -> dict:
    if clean and LAKE.exists():
        shutil.rmtree(LAKE)
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    con = duckdb.connect()
    sources = load_sources()
    steps, dq = [], []

    for src in sources:
        steps.append(bronze.ingest(con, src, batch_id))
    for src in sources:
        step, metrics = silver.build(con, src)
        steps.append(step)
        dq.extend(metrics)
    steps.extend(gold.build(con))

    report = {
        "batch_id": batch_id,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sources": [{"dataset": s.name, "owner": s.owner, "classification": s.classification,
                     "load_type": s.load_type} for s in sources],
        "steps": steps,
        "data_quality": dq,
    }
    out = LAKE / "_runs" / f"{batch_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(out.relative_to(ROOT))
    return report


def main():
    r = run(clean=True)
    print(f"Run {r['batch_id']} finished. Report: {r['report_path']}\n")
    print(f"{'layer':<8}{'dataset':<28}{'rows':>8}")
    for s in r["steps"]:
        print(f"{s['layer']:<8}{s['dataset']:<28}{s['rows_out']:>8}")
    print("\nData quality (failed rows):")
    for m in r["data_quality"]:
        if m["rows_failed"]:
            print(f"  {m['dataset']:<26}{m['rule']:<22}{m['level']:<6}{m['rows_failed']:>5}")
    con = duckdb.connect()
    print("\nTop 5 highest-risk sites (gold.mart_site_risk):")
    print(con.sql(f"SELECT site_id, site_type, operator_name, major_breaches_12m, risk_score "
                  f"FROM '{(LAKE / 'gold' / 'mart_site_risk' / 'data.parquet').as_posix()}' LIMIT 5"))


if __name__ == "__main__":
    main()
