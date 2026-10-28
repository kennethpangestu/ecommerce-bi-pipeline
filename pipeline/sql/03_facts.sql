-- =============================================================================
-- FACTS
--   fact_order_items : grain = one product line in an order (transaction fact)
--   fact_orders      : grain = one order, tracking it from purchase to review
--                      (an "accumulating snapshot" fact)
-- Foreign keys are declared and enforced (PRAGMA foreign_keys = ON), so a row that
-- points at a missing dimension member fails the load instead of slipping through.
-- =============================================================================

DROP TABLE IF EXISTS fact_order_items;
CREATE TABLE fact_order_items (
    order_item_key    INTEGER PRIMARY KEY,
    order_id          TEXT    NOT NULL,                 -- degenerate dimension
    order_item_number INTEGER NOT NULL,
    purchase_date_key INTEGER NOT NULL REFERENCES dim_date (date_key),
    customer_key      INTEGER NOT NULL REFERENCES dim_customer (customer_key),
    seller_key        INTEGER NOT NULL REFERENCES dim_seller (seller_key),
    product_key       INTEGER NOT NULL REFERENCES dim_product (product_key),
    order_status      TEXT    NOT NULL,
    price             REAL    NOT NULL,
    freight_value     REAL    NOT NULL,
    shipping_limit_ts TEXT,
    UNIQUE (order_id, order_item_number)
);
INSERT INTO fact_order_items (order_id, order_item_number, purchase_date_key, customer_key,
                              seller_key, product_key, order_status, price, freight_value,
                              shipping_limit_ts)
SELECT i.order_id,
       i.order_item_number,
       CAST(strftime('%Y%m%d', o.purchase_ts) AS INTEGER),
       dc.customer_key,
       ds.seller_key,
       dp.product_key,
       o.order_status,
       i.price,
       i.freight_value,
       i.shipping_limit_ts
FROM stg_order_items i
JOIN stg_orders    o  ON o.order_id = i.order_id
JOIN stg_customers c  ON c.customer_id = o.customer_id
JOIN dim_customer  dc ON dc.customer_unique_id = c.customer_unique_id
JOIN dim_seller    ds ON ds.seller_id = i.seller_id
JOIN dim_product   dp ON dp.product_id = i.product_id;

-- Per-order rollups used by fact_orders.
DROP TABLE IF EXISTS tmp_order_items;
CREATE TEMP TABLE tmp_order_items AS
SELECT order_id,
       COUNT(*)                  AS item_count,
       COUNT(DISTINCT seller_id) AS seller_count,
       SUM(price)                AS items_value,
       SUM(freight_value)        AS freight_value,
       MAX(shipping_limit_ts)    AS shipping_limit_ts
FROM stg_order_items
GROUP BY order_id;

DROP TABLE IF EXISTS tmp_order_payments;
CREATE TEMP TABLE tmp_order_payments AS
SELECT order_id,
       SUM(payment_value)        AS payment_value,
       MAX(payment_installments) AS max_installments,
       -- the payment method that covered the most money
       MAX(CASE WHEN value_rank = 1 THEN payment_type END) AS main_payment_type
FROM (
    SELECT order_id, payment_type, payment_installments, payment_value,
           ROW_NUMBER() OVER (PARTITION BY order_id
                              ORDER BY payment_value DESC, payment_sequential) AS value_rank
    FROM stg_payments
)
GROUP BY order_id;

-- Order base: adds the person behind each order and the order's position in that
-- person's purchase history (1 = first order).
DROP TABLE IF EXISTS tmp_order_base;
CREATE TEMP TABLE tmp_order_base AS
SELECT o.*,
       c.customer_unique_id,
       CASE WHEN o.order_status = 'delivered' AND o.delivered_ts IS NOT NULL THEN 1 ELSE 0 END AS is_delivered,
       ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id
                          ORDER BY o.purchase_ts, o.order_id) AS customer_order_seq
FROM stg_orders o
JOIN stg_customers c ON c.customer_id = o.customer_id;

DROP TABLE IF EXISTS fact_orders;
CREATE TABLE fact_orders (
    order_id               TEXT    PRIMARY KEY,
    customer_key           INTEGER NOT NULL REFERENCES dim_customer (customer_key),
    purchase_date_key      INTEGER NOT NULL REFERENCES dim_date (date_key),
    delivered_date_key     INTEGER          REFERENCES dim_date (date_key),
    estimated_date_key     INTEGER          REFERENCES dim_date (date_key),
    order_status           TEXT    NOT NULL,
    purchase_ts            TEXT    NOT NULL,
    carrier_ts             TEXT,
    delivered_ts           TEXT,
    customer_order_seq     INTEGER NOT NULL,  -- 1 = the customer's first order
    item_count             INTEGER NOT NULL,
    seller_count           INTEGER NOT NULL,
    items_value            REAL    NOT NULL,
    freight_value          REAL    NOT NULL,
    payment_value          REAL,
    max_installments       INTEGER,
    main_payment_type      TEXT,
    -- delivery measures: only set for delivered orders that have a delivery date
    is_delivered           INTEGER NOT NULL CHECK (is_delivered IN (0, 1)),
    delivery_days          REAL,     -- purchase -> customer receives it
    promised_days          REAL,     -- purchase -> estimated delivery date shown to the customer
    days_late              INTEGER,  -- delivered date - estimated date (negative = early)
    is_late                INTEGER CHECK (is_late IN (0, 1)),
    seller_handoff_late    INTEGER CHECK (seller_handoff_late IN (0, 1)),  -- handed to carrier after the seller's deadline
    review_score           INTEGER CHECK (review_score BETWEEN 1 AND 5),
    is_low_review          INTEGER CHECK (is_low_review IN (0, 1))          -- 1 or 2 stars
);
INSERT INTO fact_orders
SELECT o.order_id,
       dc.customer_key,
       CAST(strftime('%Y%m%d', o.purchase_ts) AS INTEGER),
       CAST(strftime('%Y%m%d', o.delivered_ts) AS INTEGER),
       CAST(strftime('%Y%m%d', o.estimated_delivery_date) AS INTEGER),
       o.order_status,
       o.purchase_ts,
       o.carrier_ts,
       o.delivered_ts,
       o.customer_order_seq,
       COALESCE(i.item_count, 0),
       COALESCE(i.seller_count, 0),
       COALESCE(i.items_value, 0),
       COALESCE(i.freight_value, 0),
       p.payment_value,
       p.max_installments,
       p.main_payment_type,
       o.is_delivered,
       CASE WHEN o.is_delivered = 1 THEN ROUND(julianday(o.delivered_ts) - julianday(o.purchase_ts), 2) END,
       CASE WHEN o.is_delivered = 1 THEN ROUND(julianday(o.estimated_delivery_date) - julianday(o.purchase_ts), 2) END,
       CASE WHEN o.is_delivered = 1
            THEN CAST(julianday(date(o.delivered_ts)) - julianday(o.estimated_delivery_date) AS INTEGER) END,
       CASE WHEN o.is_delivered = 1
            THEN CASE WHEN date(o.delivered_ts) > o.estimated_delivery_date THEN 1 ELSE 0 END END,
       CASE WHEN o.carrier_ts IS NOT NULL AND i.shipping_limit_ts IS NOT NULL
            THEN CASE WHEN o.carrier_ts > i.shipping_limit_ts THEN 1 ELSE 0 END END,
       r.review_score,
       CASE WHEN r.review_score IS NOT NULL THEN CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END END
FROM tmp_order_base o
JOIN dim_customer dc ON dc.customer_unique_id = o.customer_unique_id
LEFT JOIN tmp_order_items    i ON i.order_id = o.order_id
LEFT JOIN tmp_order_payments p ON p.order_id = o.order_id
LEFT JOIN stg_reviews        r ON r.order_id = o.order_id;

-- Indexes on the foreign keys and the most common filters. See analysis/benchmark.py
-- for the measured effect.
CREATE INDEX ix_items_seller   ON fact_order_items (seller_key);
CREATE INDEX ix_items_product  ON fact_order_items (product_key);
CREATE INDEX ix_items_date     ON fact_order_items (purchase_date_key);
CREATE INDEX ix_items_order    ON fact_order_items (order_id);
CREATE INDEX ix_orders_date    ON fact_orders (purchase_date_key);
CREATE INDEX ix_orders_cust    ON fact_orders (customer_key);
