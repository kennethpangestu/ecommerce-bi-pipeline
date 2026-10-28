-- Q6. How accurate is the delivery promise? Compare the promised delivery window
--     with the actual one, by month: a padded promise protects on-time rate but
--     can cost sales, because shoppers see a slower delivery estimate.
SELECT d.year_month,
       COUNT(*)                                              AS delivered_orders,
       ROUND(AVG(f.promised_days), 1)                        AS avg_promised_days,
       ROUND(AVG(f.delivery_days), 1)                        AS avg_actual_days,
       ROUND(AVG(f.promised_days - f.delivery_days), 1)      AS avg_buffer_days,
       ROUND(1 - AVG(f.is_late), 3)                          AS on_time_rate
FROM fact_orders f
JOIN dim_date d ON d.date_key = f.purchase_date_key
WHERE f.is_delivered = 1 AND d.year_month BETWEEN '2017-01' AND '2018-08'
GROUP BY d.year_month
ORDER BY d.year_month;
