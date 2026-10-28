# Data model

The warehouse has four layers, each built from the one before it by the SQL files in `pipeline/sql/`:

| Layer | Tables | Purpose |
|---|---|---|
| **Raw** | `raw_*` (8 tables) | Source CSVs loaded as-is (all text). The warehouse can always be rebuilt from here. |
| **Staging** | `stg_*` (7 tables) | Typed, cleaned, one row per entity. All cleaning rules live in `01_staging.sql`. |
| **Star schema** | `dim_*` (4), `fact_*` (2) | The model analysts query. Integer surrogate keys, enforced foreign keys. |
| **Marts** | `mart_*` (5) | Small pre-aggregated tables for dashboards and recurring reports. |

## Star schema

```mermaid
erDiagram
    dim_date     ||--o{ fact_orders      : "purchase / delivered / estimated date"
    dim_customer ||--o{ fact_orders      : "placed by"
    dim_date     ||--o{ fact_order_items : "purchase date"
    dim_customer ||--o{ fact_order_items : "bought by"
    dim_seller   ||--o{ fact_order_items : "sold by"
    dim_product  ||--o{ fact_order_items : "product"
    fact_orders  ||--o{ fact_order_items : "order_id (degenerate dimension)"

    fact_orders {
        text    order_id PK
        int     customer_key FK
        int     purchase_date_key FK
        int     delivered_date_key FK
        int     estimated_date_key FK
        text    order_status
        int     customer_order_seq
        int     item_count
        int     seller_count
        real    items_value
        real    freight_value
        real    payment_value
        int     is_delivered
        real    delivery_days
        real    promised_days
        int     days_late
        int     is_late
        int     seller_handoff_late
        int     review_score
        int     is_low_review
    }
    fact_order_items {
        int     order_item_key PK
        text    order_id
        int     order_item_number
        int     purchase_date_key FK
        int     customer_key FK
        int     seller_key FK
        int     product_key FK
        real    price
        real    freight_value
    }
    dim_customer {
        int     customer_key PK
        text    customer_unique_id
        text    city
        text    state
        text    first_purchase_date
        int     lifetime_orders
    }
    dim_seller {
        int     seller_key PK
        text    seller_id
        text    city
        text    state
    }
    dim_product {
        int     product_key PK
        text    product_id
        text    category
        real    weight_g
        real    volume_cm3
    }
    dim_date {
        int     date_key PK
        text    full_date
        int     year
        int     quarter
        text    year_month
        int     day_of_week
        int     is_weekend
    }
```

## Grain of each fact table

- **`fact_order_items`**: one row per product line in an order (112,650 rows). Use it for anything about products, categories or sellers.
- **`fact_orders`**: one row per order (99,441 rows). This is an *accumulating snapshot*: it follows each order from purchase through carrier handoff and delivery to review, so delivery and review measures sit on one row. Use it for anything about orders, customers, delivery or reviews.

Keeping two grains avoids a classic BI bug: summing an order-level value (like freight or review score) from an item-level table counts multi-item orders more than once.

## Design decisions

| Decision | Why |
|---|---|
| `dim_customer` is keyed on `customer_unique_id`, not `customer_id` | The source issues a new `customer_id` for every order. Keying on it would count 99,441 "customers" instead of 96,096 people and make repeat purchases invisible. |
| Integer `date_key` (e.g. `20180315`) joined to `dim_date` | Cheap integer joins, plus ready-made calendar attributes (month, quarter, weekday) without date math in every query. |
| Delivery measures (`is_late`, `days_late`, `seller_handoff_late`) are computed once at load time | Every report uses the same definition of "late", and queries don't recompute date differences row by row. |
| `seller_handoff_late` compares the carrier pickup time with the seller's shipping deadline | Splits lateness into seller-caused and carrier-caused, so each team gets an actionable number. |
| Seller delivery and review metrics use single-seller orders only | A late or badly reviewed order with two sellers can't be blamed on either one. That's 98.7% of orders. |
| Foreign keys and `CHECK` constraints are declared and enforced | A broken row fails the load instead of silently producing wrong dashboards. |
| Indexes on fact foreign keys and date keys | Turns filtered lookups from full scans into index searches (see `analysis/benchmark.py`). |
| Full rebuild with an explicit teardown step | At this size (about 13 seconds) a full rebuild is simpler and safer than incremental loads; the teardown drops tables in dependency order so foreign keys never block a rebuild. |
