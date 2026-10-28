-- =============================================================================
-- STAGING: typed, cleaned, one row per business entity.
-- Every cleaning rule is here, in one place, with the reason next to it.
-- =============================================================================

-- Orders: one row per order. Timestamps stay as ISO-8601 text ('YYYY-MM-DD HH:MM:SS'),
-- which SQLite's date functions read directly.
DROP TABLE IF EXISTS stg_orders;
CREATE TABLE stg_orders (
    order_id                TEXT PRIMARY KEY,
    customer_id             TEXT NOT NULL,
    order_status            TEXT NOT NULL,
    purchase_ts             TEXT NOT NULL,
    approved_ts             TEXT,
    carrier_ts              TEXT,
    delivered_ts            TEXT,
    estimated_delivery_date TEXT
);
INSERT INTO stg_orders
SELECT order_id,
       customer_id,
       order_status,
       order_purchase_timestamp,
       order_approved_at,
       order_delivered_carrier_date,
       order_delivered_customer_date,
       date(order_estimated_delivery_date)
FROM raw_orders;

-- Order items: one row per product line in an order.
DROP TABLE IF EXISTS stg_order_items;
CREATE TABLE stg_order_items (
    order_id          TEXT    NOT NULL,
    order_item_number INTEGER NOT NULL,
    product_id        TEXT    NOT NULL,
    seller_id         TEXT    NOT NULL,
    shipping_limit_ts TEXT,
    price             REAL    NOT NULL CHECK (price >= 0),
    freight_value     REAL    NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_number)
);
INSERT INTO stg_order_items
SELECT order_id,
       CAST(order_item_id AS INTEGER),
       product_id,
       seller_id,
       shipping_limit_date,
       CAST(price AS REAL),
       CAST(freight_value AS REAL)
FROM raw_order_items;

-- Payments: an order can be paid in several parts (e.g. a voucher plus a card).
DROP TABLE IF EXISTS stg_payments;
CREATE TABLE stg_payments (
    order_id             TEXT    NOT NULL,
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT    NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value        REAL    NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);
INSERT INTO stg_payments
SELECT order_id,
       CAST(payment_sequential AS INTEGER),
       payment_type,
       CAST(payment_installments AS INTEGER),
       CAST(payment_value AS REAL)
FROM raw_order_payments;

-- Reviews: the source has 827 duplicated review IDs and 555 orders with more than
-- one review. Rule: keep ONE review per order, the most recently answered one
-- (ties broken by review_id so the result is deterministic).
DROP TABLE IF EXISTS stg_reviews;
CREATE TABLE stg_reviews (
    order_id         TEXT PRIMARY KEY,
    review_id        TEXT    NOT NULL,
    review_score     INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    has_comment      INTEGER NOT NULL CHECK (has_comment IN (0, 1)),
    review_created_ts TEXT,
    review_answer_ts TEXT
);
INSERT INTO stg_reviews
SELECT order_id, review_id, review_score, has_comment, review_creation_date, review_answer_timestamp
FROM (
    SELECT order_id,
           review_id,
           CAST(review_score AS INTEGER) AS review_score,
           CASE WHEN review_comment_message IS NOT NULL THEN 1 ELSE 0 END AS has_comment,
           review_creation_date,
           review_answer_timestamp,
           ROW_NUMBER() OVER (PARTITION BY order_id
                              ORDER BY review_answer_timestamp DESC, review_id DESC) AS rn
    FROM raw_order_reviews
)
WHERE rn = 1;

-- Customers: customer_id is created per ORDER; customer_unique_id is the actual person.
-- Counting customer_id would overstate customers and hide repeat purchases.
DROP TABLE IF EXISTS stg_customers;
CREATE TABLE stg_customers (
    customer_id        TEXT PRIMARY KEY,
    customer_unique_id TEXT NOT NULL,
    zip_prefix         TEXT,
    city               TEXT,
    state              TEXT
);
INSERT INTO stg_customers
SELECT customer_id, customer_unique_id, customer_zip_code_prefix,
       lower(trim(customer_city)), upper(trim(customer_state))
FROM raw_customers;

-- Products: 610 products have no category -> 'unknown'. Two Portuguese categories
-- are missing from the translation file; they are translated here by hand.
DROP TABLE IF EXISTS stg_products;
CREATE TABLE stg_products (
    product_id     TEXT PRIMARY KEY,
    category_pt    TEXT NOT NULL,
    category       TEXT NOT NULL,
    photos_qty     INTEGER,
    weight_g       REAL,
    volume_cm3     REAL
);
INSERT INTO stg_products
SELECT p.product_id,
       COALESCE(p.product_category_name, 'unknown'),
       COALESCE(t.product_category_name_english,
                CASE p.product_category_name
                    WHEN 'pc_gamer' THEN 'pc_gamer'
                    WHEN 'portateis_cozinha_e_preparadores_de_alimentos' THEN 'portable_kitchen_appliances'
                END,
                'unknown'),
       CAST(p.product_photos_qty AS INTEGER),
       CAST(p.product_weight_g AS REAL),
       CAST(p.product_length_cm AS REAL) * CAST(p.product_height_cm AS REAL) * CAST(p.product_width_cm AS REAL)
FROM raw_products p
LEFT JOIN raw_category_translation t
       ON t.product_category_name = p.product_category_name;

DROP TABLE IF EXISTS stg_sellers;
CREATE TABLE stg_sellers (
    seller_id  TEXT PRIMARY KEY,
    zip_prefix TEXT,
    city       TEXT,
    state      TEXT
);
INSERT INTO stg_sellers
SELECT seller_id, seller_zip_code_prefix, lower(trim(seller_city)), upper(trim(seller_state))
FROM raw_sellers;
