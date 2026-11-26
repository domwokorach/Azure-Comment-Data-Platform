"""Bronze layer: land the data exactly as received, plus audit columns.

Rules (see docs/standards/ingestion-standards.md):
  * never change source values in bronze, only add metadata columns
  * every batch is kept (append only) so we can replay or audit any load
  * CSV is read as text; typing happens in silver
"""
from pathlib import Path

import duckdb

from .config import LAKE, ROOT, Source


def bronze_path(src: Source, batch_id: str) -> Path:
    return LAKE / "bronze" / src.source_system / src.entity / f"batch_id={batch_id}" / "data.parquet"


def ingest(con: duckdb.DuckDBPyConnection, src: Source, batch_id: str) -> dict:
    file = (ROOT / src.path).as_posix()
    if src.format == "csv":
        reader = f"read_csv('{file}', header=true, all_varchar=true)"
    elif src.format == "json":
        reader = f"read_json_auto('{file}', format='array')"
    else:
        raise ValueError(f"Unsupported format {src.format} for {src.name}")

    out = bronze_path(src, batch_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT *,
                   '{src.source_system}'      AS _source_system,
                   '{src.path}'               AS _source_file,
                   '{batch_id}'               AS _batch_id,
                   current_timestamp          AS _ingested_at
            FROM {reader}
        ) TO '{out.as_posix()}' (FORMAT parquet)
    """)
    rows = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]
    return {"layer": "bronze", "dataset": src.name, "rows_out": rows, "path": str(out.relative_to(ROOT))}
