-- =============================================================================
-- MARTS: small, pre-aggregated tables built from the star schema for dashboards
-- and recurring reports. Dashboards query a few hundred mart rows instead of
-- re-joining ~100k-row facts on every page load.
--
-- Metric definitions (also in docs/metrics.md):
--   valid order : order_status NOT IN ('canceled', 'unavailable')
--   GMV         : sum of item prices (excluding freight) on valid orders
--   AOV         : GMV / valid orders
--   on-time     : delivered on or before the estimated delivery date shown at purchase
--   low review  : 1 or 2 stars
-- =============================================================================

DROP VIEW IF EXISTS v_valid_orders;
CREATE VIEW v_valid_orders AS
SELECT * FROM fact_orders WHERE order_status NOT IN ('canceled', 'unavailable');

-- Monthly KPIs -----------------------------------------------------------------
DROP TABLE IF EXISTS mart_monthly_kpis;
CREATE TABLE mart_monthly_kpis AS
WITH placed AS (
    -- every order placed, including canceled and unavailable ones
    SELECT d.year_month, COUNT(*) AS orders_placed
    FROM fact_orders f
    JOIN dim_date d ON d.date_key = f.purchase_date_key
    GROUP BY d.year_month
),
monthly AS (
    -- all other KPIs use valid orders only, the same population as every other mart
    SELECT d.year_month,
           COUNT(*)                                                  AS valid_orders,
           SUM(f.items_value)                                        AS gmv,
           SUM(f.freight_value)                                      AS freight,
           COUNT(DISTINCT f.customer_key)                            AS active_customers,
           SUM(CASE WHEN f.customer_order_seq = 1 THEN 1 ELSE 0 END) AS new_customers,
           SUM(f.is_delivered)                                       AS delivered_orders,
           COALESCE(SUM(f.is_late), 0)                               AS late_orders,
           AVG(f.delivery_days)                                      AS avg_delivery_days,
           COUNT(f.review_score)                                     AS reviews,
           AVG(f.review_score)                                       AS avg_review,
           AVG(f.is_low_review)                                      AS low_review_rate
    FROM v_valid_orders f
    JOIN dim_date d ON d.date_key = f.purchase_date_key
    GROUP BY d.year_month
)
SELECT p.year_month,
       CASE WHEN p.year_month BETWEEN '2017-01' AND '2018-08' THEN 1 ELSE 0 END AS is_complete_month,
       p.orders_placed,
       COALESCE(m.valid_orders, 0)                           AS valid_orders,
       ROUND(COALESCE(m.gmv, 0), 2)                          AS gmv,
       ROUND(COALESCE(m.freight, 0), 2)                      AS freight,
       ROUND(m.gmv / NULLIF(m.valid_orders, 0), 2)           AS aov,
       COALESCE(m.active_customers, 0)                       AS active_customers,
       COALESCE(m.new_customers, 0)                          AS new_customers,
       COALESCE(m.delivered_orders, 0)                       AS delivered_orders,
       COALESCE(m.late_orders, 0)                            AS late_orders,
       ROUND(1.0 - CAST(m.late_orders AS REAL) / NULLIF(m.delivered_orders, 0), 4) AS on_time_rate,
       ROUND(m.avg_delivery_days, 2)                         AS avg_delivery_days,
       COALESCE(m.reviews, 0)                                AS reviews,
       ROUND(m.avg_review, 3)                                AS avg_review,
       ROUND(m.low_review_rate, 4)                           AS low_review_rate,
       ROUND(m.gmv / NULLIF(LAG(m.gmv) OVER (ORDER BY p.year_month), 0) - 1, 4) AS gmv_mom_growth
FROM placed p
LEFT JOIN monthly m ON m.year_month = p.year_month
ORDER BY p.year_month;

-- Customer state x month (lets the dashboard filter by state without the facts) --
DROP TABLE IF EXISTS mart_state_month;
CREATE TABLE mart_state_month AS
SELECT c.state                                  AS customer_state,
       d.year_month,
       COUNT(*)                                 AS valid_orders,
       ROUND(SUM(f.items_value), 2)             AS gmv,
       SUM(f.is_delivered)                      AS delivered_orders,
       COALESCE(SUM(f.is_late), 0)              AS late_orders,
       ROUND(COALESCE(SUM(f.delivery_days), 0), 2) AS delivery_days_sum,
       COUNT(f.review_score)                    AS reviews,
       COALESCE(SUM(f.review_score), 0)         AS review_score_sum,
       COALESCE(SUM(f.is_low_review), 0)        AS low_reviews
FROM v_valid_orders f
JOIN dim_customer c ON c.customer_key = f.customer_key
JOIN dim_date     d ON d.date_key = f.purchase_date_key
GROUP BY c.state, d.year_month;

-- Review score by how late (or early) the delivery was ------------------------------
DROP TABLE IF EXISTS mart_delay_reviews;
CREATE TABLE mart_delay_reviews AS
SELECT bucket_order,
       delay_bucket,
       COUNT(*)                      AS orders,
       ROUND(AVG(review_score), 3)   AS avg_review,
       ROUND(AVG(is_low_review), 4)  AS low_review_rate
FROM (
    SELECT review_score, is_low_review,
           CASE WHEN days_late <= -7 THEN 1 WHEN days_late < 0 THEN 2 WHEN days_late = 0 THEN 3
                WHEN days_late <= 3 THEN 4 WHEN days_late <= 7 THEN 5 WHEN days_late <= 14 THEN 6
                ELSE 7 END AS bucket_order,
           CASE WHEN days_late <= -7 THEN '7+ days early' WHEN days_late < 0 THEN '1-6 days early'
                WHEN days_late = 0 THEN 'On the promised day' WHEN days_late <= 3 THEN '1-3 days late'
                WHEN days_late <= 7 THEN '4-7 days late' WHEN days_late <= 14 THEN '8-14 days late'
                ELSE '15+ days late' END AS delay_bucket
    FROM fact_orders
    WHERE is_delivered = 1 AND review_score IS NOT NULL
)
GROUP BY bucket_order, delay_bucket
ORDER BY bucket_order;

-- Seller scorecard -------------------------------------------------------------------
-- Delivery and review metrics use single-seller orders only, so a late order or bad
-- review is never blamed on a seller who shared the order with someone else.
DROP TABLE IF EXISTS mart_seller_performance;
CREATE TABLE mart_seller_performance AS
WITH seller_orders AS (
    SELECT DISTINCT i.seller_key, i.order_id
    FROM fact_order_items i
    WHERE i.order_status NOT IN ('canceled', 'unavailable')
),
sales AS (
    SELECT i.seller_key,
           COUNT(*)                 AS items_sold,
           ROUND(SUM(i.price), 2)   AS gmv
    FROM fact_order_items i
    WHERE i.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY i.seller_key
),
service AS (
    SELECT so.seller_key,
           COUNT(*)                       AS orders,
           SUM(CASE WHEN f.seller_count = 1 THEN f.is_delivered ELSE 0 END)         AS delivered_single_seller,
           SUM(CASE WHEN f.seller_count = 1 THEN f.is_late ELSE 0 END)              AS late_single_seller,
           SUM(CASE WHEN f.seller_count = 1 THEN f.seller_handoff_late ELSE 0 END)  AS handoff_late_single_seller,
           SUM(CASE WHEN f.seller_count = 1 AND f.seller_handoff_late IS NOT NULL THEN 1 ELSE 0 END) AS handoff_known_single_seller,
           AVG(CASE WHEN f.seller_count = 1 THEN f.review_score END)                AS avg_review
    FROM seller_orders so
    JOIN fact_orders f ON f.order_id = so.order_id
    GROUP BY so.seller_key
)
SELECT s.seller_id,
       s.state                                   AS seller_state,
       sv.orders,
       sa.items_sold,
       sa.gmv,
       RANK() OVER (ORDER BY sa.gmv DESC)        AS gmv_rank,
       ROUND(SUM(sa.gmv) OVER (ORDER BY sa.gmv DESC, s.seller_id ROWS UNBOUNDED PRECEDING)
             / SUM(sa.gmv) OVER (), 4)           AS cumulative_gmv_share,
       sv.delivered_single_seller,
       ROUND(CAST(sv.late_single_seller AS REAL) / NULLIF(sv.delivered_single_seller, 0), 4) AS late_rate,
       ROUND(CAST(sv.handoff_late_single_seller AS REAL) / NULLIF(sv.handoff_known_single_seller, 0), 4) AS handoff_late_rate,
       ROUND(sv.avg_review, 3)                   AS avg_review
FROM sales sa
JOIN service    sv ON sv.seller_key = sa.seller_key
JOIN dim_seller s  ON s.seller_key = sa.seller_key
ORDER BY sa.gmv DESC;

-- Category performance ---------------------------------------------------------------
DROP TABLE IF EXISTS mart_category_performance;
CREATE TABLE mart_category_performance AS
SELECT p.category,
       COUNT(DISTINCT i.order_id)                                   AS orders,
       COUNT(*)                                                     AS items_sold,
       ROUND(SUM(i.price), 2)                                       AS gmv,
       ROUND(AVG(i.price), 2)                                       AS avg_item_price,
       ROUND(SUM(i.freight_value) / SUM(i.price + i.freight_value), 4) AS freight_share_of_cost,
       ROUND(AVG(f.is_late), 4)                                     AS late_rate,
       ROUND(AVG(f.review_score), 3)                                AS avg_review
FROM fact_order_items i
JOIN dim_product p ON p.product_key = i.product_key
JOIN fact_orders f ON f.order_id = i.order_id
WHERE i.order_status NOT IN ('canceled', 'unavailable')
GROUP BY p.category
ORDER BY gmv DESC;
