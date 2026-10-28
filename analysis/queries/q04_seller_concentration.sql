-- Q4. How concentrated is revenue? Sellers grouped into GMV deciles (NTILE),
--     with each decile's share of total GMV and its service quality.
WITH ranked AS (
    SELECT seller_id, gmv, late_rate, avg_review,
           NTILE(10) OVER (ORDER BY gmv DESC) AS gmv_decile
    FROM mart_seller_performance
)
SELECT gmv_decile,
       COUNT(*)                                          AS sellers,
       ROUND(SUM(gmv), 0)                                AS gmv,
       ROUND(SUM(gmv) / SUM(SUM(gmv)) OVER (), 3)        AS share_of_gmv,
       ROUND(SUM(SUM(gmv)) OVER (ORDER BY gmv_decile) / SUM(SUM(gmv)) OVER (), 3) AS cumulative_share,
       ROUND(AVG(late_rate), 3)                          AS avg_late_rate,
       ROUND(AVG(avg_review), 2)                         AS avg_review
FROM ranked
GROUP BY gmv_decile
ORDER BY gmv_decile;
