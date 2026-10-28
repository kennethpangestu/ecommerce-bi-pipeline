"""End-to-end tests on a tiny hand-made dataset where every expected value is known.

The fixture deliberately includes the problems found in the real data: one person
with two customer IDs, a duplicated review, a product with no category, a category
missing from the translation file, a canceled order, a late delivery, a late
seller handoff, and an order split across two sellers.
"""

import csv
import gzip
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.extract import load_csv  # noqa: E402
from pipeline.quality import DataQualityError, run_checks  # noqa: E402
from pipeline.run import run  # noqa: E402

RAW = {
    "olist_customers_dataset.csv.gz": [
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
        ["c1", "person1", "01000", "sao paulo", "SP"],
        ["c2", "person1", "01000", "sao paulo", "SP"],   # same person, second order
        ["c3", "person2", "20000", " Rio de Janeiro ", "rj"],
    ],
    "olist_orders_dataset.csv.gz": [
        ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
         "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"],
        # on time: delivered Mar 8, promised Mar 10 -> 2 days early
        ["o1", "c1", "delivered", "2017-03-01 10:00:00", "2017-03-01 11:00:00",
         "2017-03-03 09:00:00", "2017-03-08 15:00:00", "2017-03-10 00:00:00"],
        # late: delivered Apr 15, promised Apr 12 -> 3 days late; handed to carrier after the Apr 5 deadline
        ["o2", "c2", "delivered", "2017-04-01 10:00:00", "2017-04-01 12:00:00",
         "2017-04-06 08:00:00", "2017-04-15 18:00:00", "2017-04-12 00:00:00"],
        ["o3", "c3", "canceled", "2017-04-02 09:00:00", "", "", "", "2017-04-20 00:00:00"],
    ],
    "olist_order_items_dataset.csv.gz": [
        ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
        ["o1", "1", "p1", "s1", "2017-03-04 00:00:00", "100.00", "10.00"],
        ["o2", "1", "p2", "s1", "2017-04-05 00:00:00", "50.00", "5.00"],
        ["o2", "2", "p2", "s2", "2017-04-05 00:00:00", "30.00", "5.00"],
        ["o3", "1", "p3", "s2", "2017-04-04 00:00:00", "20.00", "2.00"],
    ],
    "olist_order_payments_dataset.csv.gz": [
        ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
        ["o1", "1", "credit_card", "3", "110.00"],
        ["o2", "1", "voucher", "1", "20.00"],
        ["o2", "2", "credit_card", "2", "70.00"],
        ["o3", "1", "boleto", "1", "22.00"],
    ],
    "olist_order_reviews_dataset.csv.gz": [
        ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
         "review_creation_date", "review_answer_timestamp"],
        ["r1", "o1", "5", "", "", "2017-03-09 00:00:00", "2017-03-10 10:00:00"],
        ["r2", "o2", "1", "", "atrasou", "2017-04-16 00:00:00", "2017-04-16 10:00:00"],
        ["r2b", "o2", "3", "", "", "2017-04-19 00:00:00", "2017-04-20 10:00:00"],  # later review wins
        ["r3", "o3", "1", "", "", "2017-04-21 00:00:00", "2017-04-21 10:00:00"],
    ],
    "olist_products_dataset.csv.gz": [
        ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
         "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
        ["p1", "beleza_saude", "40", "300", "1", "200", "10", "10", "10"],
        ["p2", "pc_gamer", "40", "300", "2", "900", "20", "10", "10"],   # missing from translation file
        ["p3", "", "", "", "", "100", "5", "5", "5"],                       # no category
    ],
    "olist_sellers_dataset.csv.gz": [
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
        ["s1", "13000", "campinas", "SP"],
        ["s2", "20000", "rio de janeiro", "RJ"],
    ],
    "product_category_name_translation.csv.gz": [
        ["﻿product_category_name", "product_category_name_english"],  # byte-order mark, as in the source
        ["beleza_saude", "health_beauty"],
    ],
}


def write_raw(folder):
    os.makedirs(folder, exist_ok=True)
    for name, rows in RAW.items():
        with gzip.open(os.path.join(folder, name), "wt", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)


def build(tmp_path):
    raw = os.path.join(str(tmp_path), "raw")
    write_raw(raw)
    db = os.path.join(str(tmp_path), "wh.db")
    result = run(db, raw, verbose=False)
    return db, result


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


# ------------------------------------------------------------------- pipeline
def test_pipeline_runs_and_all_error_checks_pass(tmp_path):
    _, result = build(tmp_path)
    errors = [c for c in result["checks"] if c["severity"] == "error"]
    assert errors and all(c["passed"] for c in errors)


def test_one_customer_row_per_person_and_order_sequence(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    assert one(c, "SELECT COUNT(*) FROM dim_customer")[0] == 2
    p1 = one(c, "SELECT customer_key, lifetime_orders, first_purchase_date, city, state "
                "FROM dim_customer WHERE customer_unique_id = 'person1'")
    assert p1[1:] == (2, "2017-03-01", "sao paulo", "SP")
    seqs = c.execute("SELECT order_id, customer_order_seq FROM fact_orders WHERE customer_key = ? "
                     "ORDER BY order_id", (p1[0],)).fetchall()
    assert seqs == [("o1", 1), ("o2", 2)]
    assert one(c, "SELECT city, state FROM dim_customer WHERE customer_unique_id = 'person2'") == \
        ("rio de janeiro", "RJ")


def test_duplicate_reviews_keep_latest_answer(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    assert one(c, "SELECT review_id, review_score FROM stg_reviews WHERE order_id = 'o2'") == ("r2b", 3)
    assert one(c, "SELECT review_score, is_low_review FROM fact_orders WHERE order_id = 'o2'") == (3, 0)


def test_category_cleaning(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    cats = dict(c.execute("SELECT product_id, category FROM dim_product").fetchall())
    assert cats == {"p1": "health_beauty", "p2": "pc_gamer", "p3": "unknown"}


def test_delivery_measures(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    o1 = one(c, "SELECT is_delivered, is_late, days_late, seller_handoff_late, delivered_date_key "
                "FROM fact_orders WHERE order_id = 'o1'")
    assert o1 == (1, 0, -2, 0, 20170308)
    o2 = one(c, "SELECT is_late, days_late, seller_handoff_late, seller_count, item_count, items_value, "
                "freight_value, payment_value, main_payment_type FROM fact_orders WHERE order_id = 'o2'")
    assert o2 == (1, 3, 1, 2, 2, 80.0, 10.0, 90.0, "credit_card")
    o3 = one(c, "SELECT is_delivered, is_late, days_late, delivery_days FROM fact_orders WHERE order_id = 'o3'")
    assert o3 == (0, None, None, None)


def test_marts_exclude_canceled_orders_and_agree(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    assert one(c, "SELECT SUM(gmv), SUM(valid_orders), SUM(orders_placed) FROM mart_monthly_kpis") == (180.0, 2, 3)
    assert one(c, "SELECT SUM(gmv), SUM(late_orders) FROM mart_state_month") == (180.0, 1)
    april = one(c, "SELECT on_time_rate, avg_review FROM mart_monthly_kpis WHERE year_month = '2017-04'")
    assert april == (0.0, 3.0)
    # late rate is only attributed to sellers on single-seller orders: o2 had two sellers
    s1 = one(c, "SELECT orders, gmv, delivered_single_seller, late_rate FROM mart_seller_performance "
                "WHERE seller_id = 's1'")
    assert s1 == (2, 150.0, 1, 0.0)


def test_rebuild_is_idempotent(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    snapshot = lambda: (c.execute("SELECT * FROM fact_orders ORDER BY order_id").fetchall(),
                        c.execute("SELECT * FROM mart_monthly_kpis ORDER BY year_month").fetchall())
    first = snapshot()
    c.close()
    run(db, os.path.join(str(tmp_path), "raw"), verbose=False)   # used to fail on foreign keys
    c = sqlite3.connect(db)
    assert snapshot() == first
    assert one(c, "SELECT COUNT(DISTINCT run_id) FROM etl_run_log")[0] == 2


def test_failed_error_check_stops_the_pipeline(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("DELETE FROM fact_order_items WHERE order_id = 'o3'")  # simulate a lost row
    with pytest.raises(DataQualityError, match="order_items_reconcile"):
        run_checks(c, "tampered-run")
    assert one(c, "SELECT passed FROM dq_results WHERE run_id = 'tampered-run' "
                  "AND check_name = 'order_items_reconcile'") == (0,)


def test_constraints_reject_bad_rows(tmp_path):
    db, _ = build(tmp_path)
    c = sqlite3.connect(db)
    c.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):   # points at a seller that doesn't exist
        c.execute("INSERT INTO fact_order_items (order_id, order_item_number, purchase_date_key, customer_key, "
                  "seller_key, product_key, order_status, price, freight_value) "
                  "VALUES ('x', 1, 20170301, 1, 999, 1, 'delivered', 1, 1)")
    with pytest.raises(sqlite3.IntegrityError):   # review score out of range
        c.execute("INSERT INTO stg_reviews VALUES ('ox', 'rx', 7, 0, NULL, NULL)")


def test_extract_rejects_malformed_rows(tmp_path):
    path = os.path.join(str(tmp_path), "bad.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("a,b\n1,2\n3\n")
    with pytest.raises(ValueError, match="expected 2 fields"):
        load_csv(sqlite3.connect(":memory:"), "raw_bad", path)
