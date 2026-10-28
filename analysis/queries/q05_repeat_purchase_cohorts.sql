-- Q5. Repeat purchases by first-purchase cohort: what share of new customers in
--     each quarter came back for a second order within 90 and 180 days?
--     (Cohorts start 2017 Q1 and end 2018 Q1 so every cohort has 180 days of data.)
WITH firsts AS (
    SELECT f.customer_key, f.purchase_ts AS first_ts
    FROM fact_orders f
    WHERE f.customer_order_seq = 1
),
seconds AS (
    SELECT f.customer_key, f.purchase_ts AS second_ts
    FROM fact_orders f
    WHERE f.customer_order_seq = 2
)
SELECT strftime('%Y', fi.first_ts) || '-Q' || ((CAST(strftime('%m', fi.first_ts) AS INTEGER) + 2) / 3) AS cohort,
       COUNT(*)                                                                         AS new_customers,
       ROUND(AVG(CASE WHEN julianday(s.second_ts) - julianday(fi.first_ts) <= 90 THEN 1.0 ELSE 0 END), 4)  AS repeat_90d,
       ROUND(AVG(CASE WHEN julianday(s.second_ts) - julianday(fi.first_ts) <= 180 THEN 1.0 ELSE 0 END), 4) AS repeat_180d
FROM firsts fi
LEFT JOIN seconds s ON s.customer_key = fi.customer_key
WHERE fi.first_ts >= '2017-01-01' AND fi.first_ts < '2018-04-01'
GROUP BY cohort
ORDER BY cohort;
