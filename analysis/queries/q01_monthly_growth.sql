-- Q1. Monthly GMV with month-over-month growth, 3-month moving average and
--     year-to-date running total (complete months only: 2017-01 to 2018-08).
WITH monthly AS (
    SELECT d.year_month,
           d.year,
           COUNT(*)            AS valid_orders,
           SUM(f.items_value)  AS gmv
    FROM v_valid_orders f
    JOIN dim_date d ON d.date_key = f.purchase_date_key
    WHERE d.year_month BETWEEN '2017-01' AND '2018-08'
    GROUP BY d.year_month, d.year
)
SELECT year_month,
       valid_orders,
       ROUND(gmv, 0)                                                         AS gmv,
       ROUND(gmv / LAG(gmv) OVER (ORDER BY year_month) - 1, 3)               AS mom_growth,
       ROUND(AVG(gmv) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0) AS gmv_3mo_avg,
       ROUND(SUM(gmv) OVER (PARTITION BY year ORDER BY year_month), 0)       AS gmv_ytd
FROM monthly
ORDER BY year_month;
