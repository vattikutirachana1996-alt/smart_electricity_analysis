-- name: a01_zscore_by_state_and_calendar_month
-- title: Z-score anomalies (same method as the Python page, executed in SQL)
-- feature: CTE chain, STDDEV_SAMP window
-- ratio = value / state's fiscal-year mean; compared with the same state and calendar month in other years.
-- Threshold here is fixed at 2.5 and groups need at least 5 years of the same month.
WITH base AS (
    SELECT st.state_name, p.period_month, p.energy_availability_mu AS v,
           CASE WHEN MONTH(p.period_month) >= 4 THEN YEAR(p.period_month) ELSE YEAR(p.period_month) - 1 END AS fy_start
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.energy_availability_mu IS NOT NULL
),
fy_mean AS (
    SELECT state_name, fy_start, AVG(v) AS m
    FROM base GROUP BY state_name, fy_start
    HAVING COUNT(*) = 12 AND AVG(v) > 0
),
ratios AS (
    SELECT b.state_name, b.period_month, MONTH(b.period_month) AS mth, b.v, f.m AS fy_mean, b.v / f.m AS ratio
    FROM base b
    JOIN fy_mean f ON f.state_name = b.state_name AND f.fy_start = b.fy_start
),
scored AS (
    SELECT r.*,
           AVG(ratio)         OVER g AS mean_ratio,
           STDDEV_SAMP(ratio) OVER g AS sd_ratio,
           COUNT(*)           OVER g AS n_grp
    FROM ratios r
    WINDOW g AS (PARTITION BY state_name, mth)
),
z AS (
    SELECT state_name, period_month, v AS observed,
           ROUND(fy_mean * mean_ratio, 2) AS baseline,
           (ratio - mean_ratio) / sd_ratio AS z_score, n_grp
    FROM scored
    WHERE n_grp >= 5 AND sd_ratio > 0
)
SELECT state_name, period_month, observed, baseline,
       ROUND(100 * (observed - baseline) / baseline, 2) AS deviation_pct,
       ROUND(z_score, 2) AS z_score, n_grp
FROM z
WHERE ABS(z_score) >= 2.5
ORDER BY ABS(z_score) DESC;

-- name: a02_largest_mom_swings
-- title: Largest absolute month-on-month swings (descriptive screening)
-- feature: LAG, ranking
WITH s AS (
    SELECT st.state_name, p.period_month, p.energy_availability_mu AS v,
           LAG(p.energy_availability_mu) OVER (PARTITION BY st.state_name ORDER BY p.period_month) AS prev_v,
           TIMESTAMPDIFF(MONTH, LAG(p.period_month) OVER (PARTITION BY st.state_name ORDER BY p.period_month), p.period_month) AS gap
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.energy_availability_mu IS NOT NULL
)
SELECT state_name, period_month, v, prev_v,
       ROUND(100 * (v - prev_v) / NULLIF(prev_v, 0), 2) AS mom_pct,
       RANK() OVER (ORDER BY ABS((v - prev_v) / NULLIF(prev_v, 0)) DESC) AS swing_rank
FROM s
WHERE gap = 1
ORDER BY swing_rank
LIMIT 25;
