-- =============================================================================
-- DIMENSIONS: the "who / what / where / when" of the star schema.
-- Each has an integer surrogate key; the source ID is kept as the natural key.
-- =============================================================================

-- Date dimension: one row per calendar day, Sept 2016 to Dec 2018.
-- date_key is an integer like 20180315, so facts can join on a cheap integer.
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,
    full_date    TEXT    NOT NULL UNIQUE,
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    year_month   TEXT    NOT NULL,
    month_name   TEXT    NOT NULL,
    day_of_week  INTEGER NOT NULL,   -- 0 = Sunday ... 6 = Saturday
    day_name     TEXT    NOT NULL,
    is_weekend   INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);
WITH RECURSIVE days(d) AS (
    SELECT '2016-09-01'
    UNION ALL
    SELECT date(d, '+1 day') FROM days WHERE d < '2018-12-31'
)
INSERT INTO dim_date
SELECT CAST(strftime('%Y%m%d', d) AS INTEGER),
       d,
       CAST(strftime('%Y', d) AS INTEGER),
       (CAST(strftime('%m', d) AS INTEGER) + 2) / 3,
       CAST(strftime('%m', d) AS INTEGER),
       strftime('%Y-%m', d),
       CASE strftime('%m', d) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Feb' WHEN '03' THEN 'Mar'
            WHEN '04' THEN 'Apr' WHEN '05' THEN 'May' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul'
            WHEN '08' THEN 'Aug' WHEN '09' THEN 'Sep' WHEN '10' THEN 'Oct' WHEN '11' THEN 'Nov'
            ELSE 'Dec' END,
       CAST(strftime('%w', d) AS INTEGER),
       CASE strftime('%w', d) WHEN '0' THEN 'Sun' WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue'
            WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu' WHEN '5' THEN 'Fri' ELSE 'Sat' END,
       CASE WHEN strftime('%w', d) IN ('0', '6') THEN 1 ELSE 0 END
FROM days;

-- Customer dimension: one row per PERSON (customer_unique_id).
-- Location comes from the person's most recent order; first purchase date is kept
-- so new vs. returning customers can be identified.
DROP TABLE IF EXISTS dim_customer;
CREATE TABLE dim_customer (
    customer_key        INTEGER PRIMARY KEY,
    customer_unique_id  TEXT    NOT NULL UNIQUE,
    city                TEXT,
    state               TEXT,
    first_purchase_date TEXT    NOT NULL,
    lifetime_orders     INTEGER NOT NULL
);
INSERT INTO dim_customer (customer_unique_id, city, state, first_purchase_date, lifetime_orders)
SELECT customer_unique_id, city, state, first_purchase_date, lifetime_orders
FROM (
    SELECT c.customer_unique_id,
           c.city,
           c.state,
           MIN(date(o.purchase_ts)) OVER (PARTITION BY c.customer_unique_id) AS first_purchase_date,
           COUNT(*) OVER (PARTITION BY c.customer_unique_id)                 AS lifetime_orders,
           ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id
                              ORDER BY o.purchase_ts DESC, o.order_id DESC)  AS rn
    FROM stg_customers c
    JOIN stg_orders o ON o.customer_id = c.customer_id
)
WHERE rn = 1
ORDER BY customer_unique_id;

DROP TABLE IF EXISTS dim_seller;
CREATE TABLE dim_seller (
    seller_key INTEGER PRIMARY KEY,
    seller_id  TEXT NOT NULL UNIQUE,
    city       TEXT,
    state      TEXT
);
INSERT INTO dim_seller (seller_id, city, state)
SELECT seller_id, city, state FROM stg_sellers ORDER BY seller_id;

DROP TABLE IF EXISTS dim_product;
CREATE TABLE dim_product (
    product_key INTEGER PRIMARY KEY,
    product_id  TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL,
    category_pt TEXT NOT NULL,
    photos_qty  INTEGER,
    weight_g    REAL,
    volume_cm3  REAL
);
INSERT INTO dim_product (product_id, category, category_pt, photos_qty, weight_g, volume_cm3)
SELECT product_id, category, category_pt, photos_qty, weight_g, volume_cm3
FROM stg_products ORDER BY product_id;
