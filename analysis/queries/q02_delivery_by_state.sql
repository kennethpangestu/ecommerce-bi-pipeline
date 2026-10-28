-- Q2. Delivery performance by customer state (states with 500+ delivered orders),
--     ranked from worst to best on-time rate.
SELECT c.state                                         AS customer_state,
       COUNT(*)                                        AS delivered_orders,
       ROUND(1 - AVG(f.is_late), 3)                    AS on_time_rate,
       ROUND(AVG(f.delivery_days), 1)                  AS avg_delivery_days,
       ROUND(AVG(f.promised_days), 1)                  AS avg_promised_days,
       ROUND(AVG(f.review_score), 2)                   AS avg_review,
       RANK() OVER (ORDER BY AVG(f.is_late) DESC)      AS worst_rank
FROM fact_orders f
JOIN dim_customer c ON c.customer_key = f.customer_key
WHERE f.is_delivered = 1
GROUP BY c.state
HAVING COUNT(*) >= 500
ORDER BY worst_rank;
