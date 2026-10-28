"""Measure what the warehouse design buys in query speed.

Each business question is answered three ways:
  1. RAW   - straight from the source-shaped raw tables (all text, string dates,
             joins on long text IDs, calculations repeated in every query)
  2. STAR  - from the star schema (typed columns, integer date keys, delivery
             measures computed once at load time)
  3. MART  - from the pre-aggregated mart a dashboard would read

It also times a point lookup (one seller's order history) with and without the
index on fact_order_items.seller_key, and shows SQLite's query plan for each.

Usage:  python analysis/benchmark.py [path/to/warehouse.db]
Timings are the median of several runs and will differ by machine; the ratios
are what matter.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUESTIONS = {
    "Monthly GMV and on-time rate": {
        "RAW": """
            SELECT strftime('%Y-%m', o.order_purchase_timestamp) AS ym,
                   SUM(i.gmv) AS gmv,
                   1 - AVG(CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
                                THEN CASE WHEN date(o.order_delivered_customer_date) > date(o.order_estimated_delivery_date)
                                          THEN 1.0 ELSE 0.0 END END) AS on_time
            FROM raw_orders o
            LEFT JOIN (SELECT order_id, SUM(CAST(price AS REAL)) AS gmv FROM raw_order_items GROUP BY order_id) i
                   ON i.order_id = o.order_id
            WHERE o.order_status NOT IN ('canceled', 'unavailable')
            GROUP BY ym ORDER BY ym""",
        "STAR": """
            SELECT d.year_month, SUM(f.items_value) AS gmv, 1 - AVG(f.is_late) AS on_time
            FROM fact_orders f JOIN dim_date d ON d.date_key = f.purchase_date_key
            WHERE f.order_status NOT IN ('canceled', 'unavailable')
            GROUP BY d.year_month ORDER BY d.year_month""",
        "MART": "SELECT year_month, gmv, on_time_rate FROM mart_monthly_kpis ORDER BY year_month",
    },
    "Top 20 sellers by GMV with late rate": {
        "RAW": """
            WITH so AS (
                SELECT i.seller_id, i.order_id, SUM(CAST(i.price AS REAL)) AS gmv
                FROM raw_order_items i GROUP BY i.seller_id, i.order_id
            )
            SELECT so.seller_id, SUM(so.gmv) AS gmv,
                   AVG(CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
                            THEN CASE WHEN date(o.order_delivered_customer_date) > date(o.order_estimated_delivery_date)
                                      THEN 1.0 ELSE 0.0 END END) AS late_rate
            FROM so JOIN raw_orders o ON o.order_id = so.order_id
            WHERE o.order_status NOT IN ('canceled', 'unavailable')
            GROUP BY so.seller_id ORDER BY gmv DESC LIMIT 20""",
        "STAR": """
            SELECT s.seller_id, SUM(i.price) AS gmv, AVG(f.is_late) AS late_rate
            FROM fact_order_items i
            JOIN fact_orders f ON f.order_id = i.order_id
            JOIN dim_seller s  ON s.seller_key = i.seller_key
            WHERE i.order_status NOT IN ('canceled', 'unavailable')
            GROUP BY s.seller_id ORDER BY gmv DESC LIMIT 20""",
        "MART": "SELECT seller_id, gmv, late_rate FROM mart_seller_performance ORDER BY gmv DESC LIMIT 20",
    },
}

LOOKUP = """
    SELECT i.order_id, i.price, f.purchase_ts, f.is_late, f.review_score
    FROM fact_order_items i JOIN fact_orders f ON f.order_id = i.order_id
    WHERE i.seller_key = ?"""


def timed(conn, sql, params=(), runs=7) -> float:
    conn.execute(sql, params).fetchall()  # warm-up so every variant starts with a warm cache
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        conn.execute(sql, params).fetchall()
        times.append(time.perf_counter() - t)
    return statistics.median(times) * 1000


def plan(conn, sql, params=()) -> str:
    return "; ".join(row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def run(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    results = {"questions": [], "lookup": {}}
    for question, variants in QUESTIONS.items():
        row = {"question": question}
        for name, sql in variants.items():
            row[name] = timed(conn, sql)
        row["rows_read_by_dashboard"] = conn.execute(
            f"SELECT COUNT(*) FROM ({variants['MART'].replace('LIMIT 20', '')})").fetchone()[0]
        results["questions"].append(row)

    # Point lookup, with the index (as built) vs without it (on an in-memory copy).
    seller_key = conn.execute(
        "SELECT seller_key FROM fact_order_items GROUP BY seller_key ORDER BY COUNT(*) DESC LIMIT 1 OFFSET 50"
    ).fetchone()[0]
    with_index_ms = timed(conn, LOOKUP, (seller_key,))
    with_index_plan = plan(conn, LOOKUP, (seller_key,))
    mem = sqlite3.connect(":memory:")
    conn.backup(mem)
    mem.execute("DROP INDEX ix_items_seller")
    mem.execute("ANALYZE")
    no_index_ms = timed(mem, LOOKUP, (seller_key,))
    no_index_plan = plan(mem, LOOKUP, (seller_key,))
    results["lookup"] = {"with_index_ms": with_index_ms, "no_index_ms": no_index_ms,
                         "with_index_plan": with_index_plan, "no_index_plan": no_index_plan}
    return results


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "warehouse.db")
    r = run(db)
    print(f"{'Question':<40}{'RAW ms':>10}{'STAR ms':>10}{'MART ms':>10}{'raw/star':>10}")
    for q in r["questions"]:
        print(f"{q['question']:<40}{q['RAW']:>10.1f}{q['STAR']:>10.1f}{q['MART']:>10.2f}"
              f"{q['RAW'] / q['STAR']:>9.1f}x")
    lk = r["lookup"]
    print(f"\nOne seller's order history: {lk['no_index_ms']:.2f} ms without index -> "
          f"{lk['with_index_ms']:.2f} ms with index ({lk['no_index_ms'] / lk['with_index_ms']:.0f}x)")
    print("  plan without index:", lk["no_index_plan"])
    print("  plan with index:   ", lk["with_index_plan"])


if __name__ == "__main__":
    main()
