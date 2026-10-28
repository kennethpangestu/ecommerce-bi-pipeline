# Rebuilding the dashboard in Tableau or Power BI

The repo includes a working HTML dashboard (`dashboard/index.html`), but most BI teams use Tableau, Power BI or QuickSight. The CSV files in `exports/` are shaped so each tile can be rebuilt quickly.

## 1. Get the extracts

```bash
python -m pipeline.run               # build the warehouse
python -m pipeline.export --detail   # writes exports/*.csv, including orders_detail.csv
```

| File | Grain | Use for |
|---|---|---|
| `mart_state_month.csv` | customer state × month | KPI tiles, monthly trends, state filter |
| `mart_delay_reviews.csv` | delivery timing bucket | "1–2 star reviews by delivery timing" |
| `mart_seller_performance.csv` | seller | Seller scorecard table |
| `mart_category_performance.csv` | product category | Category chart |
| `mart_monthly_kpis.csv` | month | Monthly trends without a state filter |
| `orders_detail.csv` | order (~99k rows) | Ad-hoc drill-down, custom calculations |

## 2. Calculated fields

Build rates from the summed counts, never by averaging rates, so filtered totals stay correct.

| Field | Tableau | Power BI (DAX measure) |
|---|---|---|
| GMV | `SUM([gmv])` | `GMV = SUM(mart_state_month[gmv])` |
| Orders | `SUM([valid_orders])` | `Orders = SUM(mart_state_month[valid_orders])` |
| AOV | `SUM([gmv]) / SUM([valid_orders])` | `AOV = DIVIDE([GMV], [Orders])` |
| On-time rate | `1 - SUM([late_orders]) / SUM([delivered_orders])` | `On-time = 1 - DIVIDE(SUM(mart_state_month[late_orders]), SUM(mart_state_month[delivered_orders]))` |
| Average review | `SUM([review_score_sum]) / SUM([reviews])` | `Avg review = DIVIDE(SUM(mart_state_month[review_score_sum]), SUM(mart_state_month[reviews]))` |
| 1–2 star share | `SUM([low_reviews]) / SUM([reviews])` | `Low reviews % = DIVIDE(SUM(mart_state_month[low_reviews]), SUM(mart_state_month[reviews]))` |

Filter `year_month` to 2017-01 through 2018-08 (complete months).

## 3. Layout

1. **Top row: six KPI cards.** GMV, Orders, AOV, On-time rate, Average review, 1–2 star share.
2. **Filter:** `customer_state`, applied to the KPI cards and both monthly charts.
3. **Monthly GMV:** bar chart, `year_month` on the x-axis.
4. **Monthly on-time rate:** line chart, with a reference line at the overall rate.
5. **1–2 star share by delivery timing:** bars ordered by `bucket_order`; color the late buckets differently from the on-time ones.
6. **Seller table:** top 25 by GMV, with conditional formatting where `late_rate` is above the overall late rate.

## 4. Check your numbers

With no filter applied, your dashboard should show exactly:

| KPI | Value |
|---|---|
| GMV | R$ 13,449,530 |
| Orders | 97,910 |
| AOV | R$ 137 |
| On-time rate | 93.2% |
| Average review | 4.10 |
| 1–2 star share | 14.2% |

If a number differs, the usual cause is averaging a rate column instead of dividing summed counts.
