"""Build dashboard/index.html: a self-contained, interactive dashboard that reads
only the marts (a few hundred rows), never the fact tables.

Usage:  python dashboard/build_dashboard.py [path/to/warehouse.db]

The output is one HTML file with the data embedded, so it opens offline, works on
GitHub Pages, and needs no server. Filtering by customer state recomputes every KPI
and the monthly charts from mart_state_month in the browser.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIRST_MONTH, LAST_MONTH = "2017-01", "2018-08"


def rows(conn, query, params=()):
    cur = conn.execute(query, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_data(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    data = {
        "stateMonth": rows(conn, """
            SELECT customer_state AS s, year_month AS m, valid_orders AS o, gmv AS g,
                   delivered_orders AS d, late_orders AS l, reviews AS r,
                   review_score_sum AS rs, low_reviews AS lr
            FROM mart_state_month WHERE year_month BETWEEN ? AND ?
            ORDER BY customer_state, year_month""", (FIRST_MONTH, LAST_MONTH)),
        "delay": rows(conn, "SELECT delay_bucket AS b, orders AS n, low_review_rate AS rate, avg_review AS avg "
                            "FROM mart_delay_reviews ORDER BY bucket_order"),
        "sellers": rows(conn, """
            SELECT seller_id AS id, seller_state AS state, orders, gmv, late_rate AS late,
                   handoff_late_rate AS handoff, avg_review AS review
            FROM mart_seller_performance ORDER BY gmv DESC LIMIT 25"""),
        "categories": rows(conn, """
            SELECT category AS c, gmv, late_rate AS late, avg_review AS review
            FROM mart_category_performance ORDER BY gmv DESC LIMIT 12"""),
        "run": rows(conn, "SELECT MAX(run_id) AS run_id, MIN(passed) AS all_passed FROM dq_results "
                          "WHERE severity = 'error' AND run_id = (SELECT MAX(run_id) FROM dq_results)")[0],
    }
    conn.close()
    return data


def build(db_path: str, out_path: str) -> str:
    data = load_data(db_path)
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", payload)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "warehouse.db")
    print("Wrote", build(db, os.path.join(HERE, "index.html")))
