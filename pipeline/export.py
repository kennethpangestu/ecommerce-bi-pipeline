"""Export marts (and optionally an order-level extract) as CSV for Tableau or Power BI.

Usage:
    python -m pipeline.export            # marts only -> exports/
    python -m pipeline.export --detail   # also exports/orders_detail.csv (~99k rows)
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MARTS = ["mart_monthly_kpis", "mart_state_month", "mart_delay_reviews",
         "mart_seller_performance", "mart_category_performance"]

# One row per order, already joined to its dimensions: the easiest shape for a BI tool.
ORDERS_DETAIL = """
SELECT f.order_id,
       d.full_date        AS purchase_date,
       d.year_month       AS purchase_month,
       f.order_status,
       c.customer_unique_id,
       c.state            AS customer_state,
       c.city             AS customer_city,
       f.customer_order_seq,
       f.item_count,
       f.seller_count,
       f.items_value,
       f.freight_value,
       f.payment_value,
       f.main_payment_type,
       f.is_delivered,
       f.delivery_days,
       f.promised_days,
       f.days_late,
       f.is_late,
       f.seller_handoff_late,
       f.review_score,
       f.is_low_review
FROM fact_orders f
JOIN dim_customer c ON c.customer_key = f.customer_key
JOIN dim_date d     ON d.date_key = f.purchase_date_key
ORDER BY f.purchase_ts
"""


def write_query(conn: sqlite3.Connection, query: str, path: str) -> int:
    cur = conn.execute(query)
    cols = [c[0] for c in cur.description]
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for row in cur:
            w.writerow(row)
            rows += 1
    return rows


def export(db_path: str, out_dir: str, detail: bool = False) -> dict[str, int]:
    os.makedirs(out_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    counts = {}
    for mart in MARTS:
        counts[mart] = write_query(conn, f"SELECT * FROM {mart}", os.path.join(out_dir, f"{mart}.csv"))
    if detail:
        counts["orders_detail"] = write_query(conn, ORDERS_DETAIL, os.path.join(out_dir, "orders_detail.csv"))
    conn.close()
    return counts


def main():
    parser = argparse.ArgumentParser(description="Export BI extracts as CSV")
    parser.add_argument("--db", default=os.path.join(ROOT, "warehouse.db"))
    parser.add_argument("--out", default=os.path.join(ROOT, "exports"))
    parser.add_argument("--detail", action="store_true", help="also export the order-level extract")
    args = parser.parse_args()
    for name, n in export(args.db, args.out, args.detail).items():
        print(f"{name:<28}{n:>8,} rows")


if __name__ == "__main__":
    main()
