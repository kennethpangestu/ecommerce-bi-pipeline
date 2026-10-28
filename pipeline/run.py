"""Run the full ETL pipeline: extract -> staging -> star schema -> marts -> checks.

Usage:
    python -m pipeline.run                    # builds warehouse.db in the project folder
    python -m pipeline.run --db path/to.db --raw path/to/raw

The build is idempotent: every table is dropped and recreated, so running it twice
gives the same warehouse. Each step's row count and duration are logged to the
``etl_run_log`` table so slow or unexpected runs can be spotted.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from .extract import extract_all
from .quality import run_checks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql")
SQL_STEPS = ["01_staging.sql", "02_dimensions.sql", "03_facts.sql", "04_marts.sql"]

# table whose row count is logged after each SQL step
STEP_TABLES = {
    "01_staging.sql": ["stg_orders", "stg_order_items", "stg_payments", "stg_reviews",
                       "stg_customers", "stg_products", "stg_sellers"],
    "02_dimensions.sql": ["dim_date", "dim_customer", "dim_seller", "dim_product"],
    "03_facts.sql": ["fact_order_items", "fact_orders"],
    "04_marts.sql": ["mart_monthly_kpis", "mart_state_month", "mart_delay_reviews",
                     "mart_seller_performance", "mart_category_performance"],
}


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _log(conn, run_id, step, rows, seconds):
    conn.execute(
        "INSERT INTO etl_run_log (run_id, step, rows_out, seconds) VALUES (?, ?, ?, ?)",
        (run_id, step, rows, round(seconds, 3)))
    conn.commit()


def run(db_path: str, raw_dir: str, verbose: bool = True) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    say = print if verbose else (lambda *a, **k: None)
    conn = connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etl_run_log (
            run_id    TEXT NOT NULL,
            step      TEXT NOT NULL,
            rows_out  INTEGER,
            seconds   REAL,
            logged_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
    started = time.perf_counter()
    say(f"Run {run_id}")

    # Drop the previous build first: facts reference dimensions, so order matters.
    with open(os.path.join(SQL_DIR, "00_teardown.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())

    t = time.perf_counter()
    counts = extract_all(conn, raw_dir)
    for table, n in counts.items():
        _log(conn, run_id, f"extract:{table}", n, 0.0)
    _log(conn, run_id, "extract", sum(counts.values()), time.perf_counter() - t)
    say(f"  extract          {sum(counts.values()):>9,} rows  {time.perf_counter() - t:6.1f}s")

    for step in SQL_STEPS:
        t = time.perf_counter()
        with open(os.path.join(SQL_DIR, step), encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        for table in STEP_TABLES[step]:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            _log(conn, run_id, f"{step}:{table}", n, 0.0)
        elapsed = time.perf_counter() - t
        _log(conn, run_id, step, None, elapsed)
        say(f"  {step:<16} {'':>9}       {elapsed:6.1f}s")

    t = time.perf_counter()
    results = run_checks(conn, run_id)
    _log(conn, run_id, "quality_checks", len(results), time.perf_counter() - t)
    errors = sum(1 for r in results if r["severity"] == "error")
    warns = [r for r in results if r["severity"] == "warn" and not r["passed"]]
    say(f"  quality checks   {errors} error checks passed, {len(warns)} known issues logged")
    for r in warns:
        say(f"    warn: {r['description']}: {r['violations']:,}")

    conn.execute("ANALYZE")  # refresh the query planner's statistics
    conn.commit()
    total = time.perf_counter() - started
    _log(conn, run_id, "total", None, total)
    conn.close()
    say(f"Done in {total:.1f}s -> {db_path}")
    return {"run_id": run_id, "extract_counts": counts, "checks": results, "seconds": total}


def main():
    parser = argparse.ArgumentParser(description="Build the e-commerce BI warehouse")
    parser.add_argument("--db", default=os.path.join(ROOT, "warehouse.db"))
    parser.add_argument("--raw", default=os.path.join(ROOT, "data", "raw"))
    args = parser.parse_args()
    run(args.db, args.raw)


if __name__ == "__main__":
    main()
