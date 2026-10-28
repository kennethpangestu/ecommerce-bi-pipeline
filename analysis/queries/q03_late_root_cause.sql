-- Q3. Why are orders late? Split late, single-seller deliveries by where the time
--     was lost: the seller handed the parcel to the carrier after its shipping
--     deadline, or the seller was on time and the carrier leg ran over.
SELECT CASE WHEN f.seller_handoff_late = 1 THEN 'Seller handed off late'
            WHEN f.seller_handoff_late = 0 THEN 'Seller on time, carrier late'
            ELSE 'Unknown (no carrier date)' END        AS cause,
       COUNT(*)                                         AS late_orders,
       ROUND(1.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 3) AS share_of_late,
       ROUND(AVG(f.days_late), 1)                       AS avg_days_late,
       ROUND(AVG(f.review_score), 2)                    AS avg_review
FROM fact_orders f
WHERE f.is_late = 1 AND f.seller_count = 1
GROUP BY cause
ORDER BY late_orders DESC;
