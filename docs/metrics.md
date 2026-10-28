# Metric definitions

One definition per metric, used everywhere: the marts, the notebook and the dashboard. A data quality check (`marts_agree_on_gmv_and_orders`) fails the pipeline if two marts disagree.

| Metric | Definition | Source column(s) |
|---|---|---|
| **Valid order** | An order whose status is not `canceled` or `unavailable` | `fact_orders.order_status` |
| **Orders placed** | All orders, including canceled and unavailable | `mart_monthly_kpis.orders_placed` |
| **GMV** | Sum of item prices on valid orders. Excludes freight. In Brazilian reais (R$). | `fact_order_items.price`, `fact_orders.items_value` |
| **AOV** (average order value) | GMV ÷ valid orders | |
| **Freight share of cost** | Freight ÷ (price + freight) | `freight_value`, `price` |
| **Delivered order** | Status `delivered` **and** a recorded delivery date (8 orders marked delivered with no date are excluded) | `fact_orders.is_delivered` |
| **Delivery days** | Time from purchase to the customer receiving the order | `fact_orders.delivery_days` |
| **Promised days** | Time from purchase to the estimated delivery date shown to the customer | `fact_orders.promised_days` |
| **Days late** | Delivery date minus estimated date, in whole days; negative means early | `fact_orders.days_late` |
| **Late / on time** | Late if delivered on a later calendar day than the estimated date; on-time rate = 1 − late ÷ delivered | `fact_orders.is_late` |
| **Late seller handoff** | The order reached the carrier after the seller's shipping deadline | `fact_orders.seller_handoff_late` |
| **Low review** | A 1 or 2 star review | `fact_orders.is_low_review` |
| **Average review** | Mean review score (1–5) on valid orders with a review | `fact_orders.review_score` |
| **Customer** | A person (`customer_unique_id`), not a per-order `customer_id` | `dim_customer` |
| **New customer** | The order is that person's first (`customer_order_seq = 1`) | `fact_orders.customer_order_seq` |
| **Repeat rate (N days)** | Share of new customers whose second order came within N days of the first | `analysis/queries/q05_repeat_purchase_cohorts.sql` |
| **Complete month** | Jan 2017 to Aug 2018. Earlier and later months have only a handful of orders and are excluded from trends. | `mart_monthly_kpis.is_complete_month` |

## Known source data issues

Logged on every run as `warn` checks in `dq_results`:

| Issue | Rows | How it's handled |
|---|---|---|
| Duplicate reviews (827 repeated review IDs; 555 orders with 2+ reviews) | 559 removed | Keep the most recently answered review per order |
| Products with no category | 610 | Category set to `unknown` |
| Categories missing from the translation file | 2 | Translated in `01_staging.sql` |
| Orders marked delivered with no delivery date | 8 | Excluded from delivery metrics |
| Orders with no items | 775 | Kept in `fact_orders` with zero values; almost all unavailable or canceled |
| Payments differ from item + freight total by more than $1 | 250 | GMV uses item prices, which reconcile to the source to the cent |
| Carrier pickup recorded before payment approval | 1,359 | Kept; timestamps are not used for that comparison |
