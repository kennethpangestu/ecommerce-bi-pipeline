"""Extract: load the raw Olist CSV files into ``raw_*`` tables, unchanged.

The raw layer keeps every value as text, exactly as delivered, so the warehouse
can always be rebuilt from it and any cleaning decision can be traced back to
the source. The only change is that empty strings become NULL.
"""

from __future__ import annotations

import csv
import gzip
import os
import sqlite3

# raw table name -> source file
SOURCES = {
    "raw_orders": "olist_orders_dataset.csv.gz",
    "raw_order_items": "olist_order_items_dataset.csv.gz",
    "raw_order_payments": "olist_order_payments_dataset.csv.gz",
    "raw_order_reviews": "olist_order_reviews_dataset.csv.gz",
    "raw_customers": "olist_customers_dataset.csv.gz",
    "raw_products": "olist_products_dataset.csv.gz",
    "raw_sellers": "olist_sellers_dataset.csv.gz",
    "raw_category_translation": "product_category_name_translation.csv.gz",
}


def _open(path: str):
    opener = gzip.open if path.endswith(".gz") else open
    # utf-8-sig strips the byte-order mark at the start of the translation file
    return opener(path, "rt", encoding="utf-8-sig", newline="")


def load_csv(conn: sqlite3.Connection, table: str, path: str, batch_size: int = 20_000) -> int:
    """(Re)create ``table`` with one TEXT column per CSV column and load every row."""
    with _open(path) as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        cols = ", ".join(f'"{h}" TEXT' for h in header)
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(f'CREATE TABLE "{table}" ({cols})')
        placeholders = ", ".join("?" for _ in header)
        insert = f'INSERT INTO "{table}" VALUES ({placeholders})'
        rows, batch = 0, []
        for record in reader:
            if len(record) != len(header):
                raise ValueError(f"{os.path.basename(path)} line {reader.line_num}: "
                                 f"expected {len(header)} fields, got {len(record)}")
            batch.append([v if v != "" else None for v in record])
            if len(batch) >= batch_size:
                conn.executemany(insert, batch)
                rows += len(batch)
                batch = []
        if batch:
            conn.executemany(insert, batch)
            rows += len(batch)
    return rows


def extract_all(conn: sqlite3.Connection, raw_dir: str) -> dict[str, int]:
    """Load every source file; returns rows loaded per raw table."""
    counts = {}
    for table, filename in SOURCES.items():
        path = os.path.join(raw_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing source file: {path}")
        counts[table] = load_csv(conn, table, path)
    conn.commit()
    return counts
