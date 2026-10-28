"""Data quality checks that run after every load.

Each check is a SQL query that counts *violations*. ``error`` checks stop the
pipeline (the warehouse would give wrong answers); ``warn`` checks record known
issues in the source data that are handled by a documented rule but should be
watched. Every result is written to the ``dq_results`` table with the run ID.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # "error" or "warn"
    sql: str       # must return a single integer: the number of violations
    description: str


CHECKS: list[Check] = [
    # --- completeness: nothing lost between raw and warehouse ----------------------
    Check("orders_reconcile", "error",
          "SELECT ABS((SELECT COUNT(*) FROM raw_orders) - (SELECT COUNT(*) FROM fact_orders))",
          "Every raw order appears exactly once in fact_orders"),
    Check("order_items_reconcile", "error",
          "SELECT ABS((SELECT COUNT(*) FROM raw_order_items) - (SELECT COUNT(*) FROM fact_order_items))",
          "Every raw order item appears in fact_order_items"),
    Check("item_revenue_reconciles", "error",
          "SELECT CASE WHEN ABS((SELECT SUM(CAST(price AS REAL)) FROM raw_order_items)"
          " - (SELECT SUM(price) FROM fact_order_items)) < 0.01 THEN 0 ELSE 1 END",
          "Total item revenue matches the source to the cent"),
    Check("customers_reconcile", "error",
          "SELECT ABS((SELECT COUNT(DISTINCT customer_unique_id) FROM raw_customers)"
          " - (SELECT COUNT(*) FROM dim_customer))",
          "One dim_customer row per real customer (customer_unique_id)"),
    # --- uniqueness -------------------------------------------------------------------
    Check("fact_orders_pk_unique", "error",
          "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_orders",
          "order_id is unique in fact_orders"),
    Check("one_review_per_order", "error",
          "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM stg_reviews",
          "Duplicate reviews were collapsed to one per order"),
    # --- referential integrity ----------------------------------------------------------
    Check("foreign_keys_valid", "error",
          "SELECT COUNT(*) FROM pragma_foreign_key_check",
          "Every fact row points at existing dimension rows"),
    Check("purchase_dates_in_dim_date", "error",
          "SELECT COUNT(*) FROM fact_orders f LEFT JOIN dim_date d ON d.date_key = f.purchase_date_key"
          " WHERE d.date_key IS NULL",
          "Every purchase date exists in dim_date"),
    # --- validity -----------------------------------------------------------------------
    Check("delivery_after_purchase", "error",
          "SELECT COUNT(*) FROM fact_orders WHERE delivered_ts < purchase_ts",
          "No order is delivered before it was bought"),
    Check("no_negative_amounts", "error",
          "SELECT COUNT(*) FROM fact_order_items WHERE price < 0 OR freight_value < 0",
          "Prices and freight are never negative"),
    Check("delivery_measures_consistent", "error",
          "SELECT COUNT(*) FROM fact_orders WHERE (is_delivered = 1) <> (delivery_days IS NOT NULL)",
          "Delivery measures are set exactly for delivered orders"),
    # --- consistency: marts that overlap must give the same totals ------------------------
    Check("marts_agree_on_gmv_and_orders", "error",
          "SELECT CASE WHEN ABS((SELECT SUM(gmv) FROM mart_monthly_kpis) - (SELECT SUM(gmv) FROM mart_state_month)) < 0.01"
          " AND (SELECT SUM(valid_orders) FROM mart_monthly_kpis) = (SELECT SUM(valid_orders) FROM mart_state_month)"
          " AND (SELECT SUM(late_orders) FROM mart_monthly_kpis) = (SELECT SUM(late_orders) FROM mart_state_month)"
          " AND (SELECT SUM(reviews) FROM mart_monthly_kpis) = (SELECT SUM(reviews) FROM mart_state_month)"
          " THEN 0 ELSE 1 END",
          "Monthly and state marts report the same GMV, orders, late orders and reviews"),
    Check("marts_match_facts", "error",
          "SELECT CASE WHEN ABS((SELECT SUM(gmv) FROM mart_monthly_kpis)"
          " - (SELECT SUM(items_value) FROM v_valid_orders)) < 0.01 THEN 0 ELSE 1 END",
          "Mart GMV equals GMV recomputed from the fact table"),
    # --- known source issues, handled by a rule (warn) -----------------------------------
    Check("delivered_without_date", "warn",
          "SELECT COUNT(*) FROM stg_orders WHERE order_status = 'delivered' AND delivered_ts IS NULL",
          "Orders marked delivered with no delivery date (excluded from delivery metrics)"),
    Check("products_without_category", "warn",
          "SELECT COUNT(*) FROM dim_product WHERE category = 'unknown'",
          "Products with no category (labelled 'unknown')"),
    Check("payment_differs_from_items", "warn",
          "SELECT COUNT(*) FROM fact_orders WHERE payment_value IS NOT NULL AND item_count > 0"
          " AND ABS(payment_value - items_value - freight_value) > 1",
          "Orders whose payments differ from item + freight total by more than $1 (GMV uses item prices)"),
    Check("carrier_before_approval", "warn",
          "SELECT COUNT(*) FROM stg_orders WHERE carrier_ts < approved_ts",
          "Orders handed to the carrier before payment approval (timestamp entry issue)"),
    Check("orders_without_items", "warn",
          "SELECT COUNT(*) FROM fact_orders WHERE item_count = 0",
          "Orders with no items (mostly unavailable or canceled)"),
]


class DataQualityError(RuntimeError):
    pass


def run_checks(conn: sqlite3.Connection, run_id: str, checks: list[Check] | None = None) -> list[dict]:
    """Run every check, store results in ``dq_results``, and raise if any error check fails."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dq_results (
            run_id      TEXT    NOT NULL,
            check_name  TEXT    NOT NULL,
            severity    TEXT    NOT NULL,
            violations  INTEGER NOT NULL,
            passed      INTEGER NOT NULL,
            description TEXT,
            checked_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, check_name)
        )""")
    results = []
    for check in checks or CHECKS:
        violations = int(conn.execute(check.sql).fetchone()[0] or 0)
        passed = violations == 0
        results.append({"check": check.name, "severity": check.severity, "violations": violations,
                        "passed": passed, "description": check.description})
        conn.execute(
            "INSERT OR REPLACE INTO dq_results (run_id, check_name, severity, violations, passed, description)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, check.name, check.severity, violations, int(passed), check.description))
    conn.commit()
    failed = [r for r in results if r["severity"] == "error" and not r["passed"]]
    if failed:
        names = ", ".join(f"{r['check']} ({r['violations']})" for r in failed)
        raise DataQualityError(f"Data quality checks failed: {names}")
    return results
