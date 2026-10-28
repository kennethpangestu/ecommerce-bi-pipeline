-- =============================================================================
-- TEARDOWN: drop the previous build in reverse dependency order
-- (marts -> facts -> dimensions -> staging). Facts hold foreign keys to the
-- dimensions, so dropping a dimension first would violate those keys.
-- =============================================================================
DROP TABLE IF EXISTS mart_category_performance;
DROP TABLE IF EXISTS mart_seller_performance;
DROP TABLE IF EXISTS mart_delay_reviews;
DROP TABLE IF EXISTS mart_state_month;
DROP TABLE IF EXISTS mart_monthly_kpis;
DROP VIEW  IF EXISTS v_valid_orders;

DROP TABLE IF EXISTS fact_orders;
DROP TABLE IF EXISTS fact_order_items;

DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_seller;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_date;

DROP TABLE IF EXISTS stg_sellers;
DROP TABLE IF EXISTS stg_products;
DROP TABLE IF EXISTS stg_customers;
DROP TABLE IF EXISTS stg_reviews;
DROP TABLE IF EXISTS stg_payments;
DROP TABLE IF EXISTS stg_order_items;
DROP TABLE IF EXISTS stg_orders;
