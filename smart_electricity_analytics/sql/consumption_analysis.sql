-- Energy availability (MU) is used as the consumption proxy. See README for the CEA definition.
-- Each block starts with "-- name:" and is executed by the Advanced SQL page.

-- name: c01_monthly_cte_aggregation
-- title: National monthly totals (CTE aggregation)
-- feature: CTE
WITH monthly AS (
    SELECT p.period_month,
           COUNT(DISTINCT p.state_id)        AS states_reporting,
           SUM(p.energy_availability_mu)     AS availability_mu,
           SUM(p.energy_requirement_mu)      AS requirement_mu
    FROM power_supply_monthly p
    GROUP BY p.period_month
)
SELECT period_month, states_reporting, requirement_mu, availability_mu,
       ROUND(100 * (requirement_mu - availability_mu) / NULLIF(requirement_mu, 0), 2) AS deficit_pct
FROM monthly
ORDER BY period_month;

-- name: c02_lag_month_on_month
-- title: Month-on-month change with LAG()
-- feature: LAG
WITH s AS (
    SELECT st.state_name, p.period_month, p.energy_availability_mu AS value_mu
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.energy_availability_mu IS NOT NULL
)
SELECT state_name, period_month, value_mu,
       LAG(value_mu) OVER w AS prev_row_mu,
       TIMESTAMPDIFF(MONTH, LAG(period_month) OVER w, period_month) AS months_gap,
       CASE WHEN TIMESTAMPDIFF(MONTH, LAG(period_month) OVER w, period_month) = 1
            THEN ROUND(100 * (value_mu - LAG(value_mu) OVER w) / NULLIF(LAG(value_mu) OVER w, 0), 2)
       END AS mom_pct
FROM s
WINDOW w AS (PARTITION BY state_name ORDER BY period_month)
ORDER BY state_name, period_month;

-- name: c03_rank_dense_rank
-- title: State ranking per fiscal year with RANK() and DENSE_RANK()
-- feature: RANK, DENSE_RANK
WITH fy AS (
    SELECT st.state_name,
           CASE WHEN MONTH(p.period_month) >= 4 THEN YEAR(p.period_month) ELSE YEAR(p.period_month) - 1 END AS fy_start,
           SUM(p.energy_availability_mu) AS total_mu,
           COUNT(p.energy_availability_mu) AS n_months
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    GROUP BY st.state_name, fy_start
    HAVING COUNT(p.energy_availability_mu) = 12
)
SELECT fy_start, state_name, total_mu,
       RANK()       OVER (PARTITION BY fy_start ORDER BY total_mu DESC) AS rank_pos,
       DENSE_RANK() OVER (PARTITION BY fy_start ORDER BY total_mu DESC) AS dense_rank_pos
FROM fy
ORDER BY fy_start DESC, rank_pos;

-- name: c04_moving_average_3m
-- title: Three-month moving average per state
-- feature: Window frame
SELECT st.state_name, p.period_month, p.energy_availability_mu AS value_mu,
       ROUND(AVG(p.energy_availability_mu) OVER w3, 2) AS ma_3m_mu,
       TIMESTAMPDIFF(MONTH, MIN(p.period_month) OVER w3, p.period_month) AS span_months_check
FROM power_supply_monthly p
JOIN states st ON st.state_id = p.state_id
WHERE p.energy_availability_mu IS NOT NULL
WINDOW w3 AS (PARTITION BY st.state_name ORDER BY p.period_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
ORDER BY st.state_name, p.period_month;

-- name: c05_running_total_fiscal_year
-- title: Running total within each fiscal year
-- feature: SUM OVER
WITH s AS (
    SELECT st.state_name, p.period_month, p.energy_availability_mu AS value_mu,
           CASE WHEN MONTH(p.period_month) >= 4 THEN YEAR(p.period_month) ELSE YEAR(p.period_month) - 1 END AS fy_start
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.energy_availability_mu IS NOT NULL
)
SELECT state_name, fy_start, period_month, value_mu,
       SUM(value_mu) OVER (PARTITION BY state_name, fy_start ORDER BY period_month
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total_mu
FROM s
ORDER BY state_name, period_month;

-- name: c06_year_on_year_self_join
-- title: Year-on-year growth (self-join on same month last year)
-- feature: Self join
SELECT st.state_name, cur.period_month,
       cur.energy_availability_mu  AS current_mu,
       prev.energy_availability_mu AS same_month_last_year_mu,
       ROUND(100 * (cur.energy_availability_mu - prev.energy_availability_mu)
             / NULLIF(prev.energy_availability_mu, 0), 2) AS yoy_pct
FROM power_supply_monthly cur
JOIN states st ON st.state_id = cur.state_id
LEFT JOIN power_supply_monthly prev
       ON prev.state_id = cur.state_id
      AND prev.period_month = DATE_SUB(cur.period_month, INTERVAL 1 YEAR)
WHERE prev.record_id IS NOT NULL
ORDER BY st.state_name, cur.period_month;

-- name: c07_multi_table_join
-- title: Region summary joining regions, states, facts and data sources
-- feature: Multi-table JOIN
SELECT r.region_name,
       ds.dataset_name,
       COUNT(DISTINCT st.state_id)       AS states,
       MIN(p.period_month)               AS first_month,
       MAX(p.period_month)               AS last_month,
       ROUND(SUM(p.energy_availability_mu), 0) AS availability_mu
FROM power_supply_monthly p
JOIN states st       ON st.state_id  = p.state_id
JOIN regions r       ON r.region_id  = st.region_id
JOIN data_sources ds ON ds.source_id = p.source_id
GROUP BY r.region_name, ds.dataset_name
ORDER BY availability_mu DESC;

-- name: c08_top_bottom_states
-- title: Top 5 and bottom 5 states in the latest complete fiscal year
-- feature: ROW_NUMBER, CTE
WITH fy AS (
    SELECT st.state_name,
           CASE WHEN MONTH(p.period_month) >= 4 THEN YEAR(p.period_month) ELSE YEAR(p.period_month) - 1 END AS fy_start,
           SUM(p.energy_availability_mu) AS total_mu
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    GROUP BY st.state_name, fy_start
    HAVING COUNT(p.energy_availability_mu) = 12
),
latest AS (SELECT * FROM fy WHERE fy_start = (SELECT MAX(fy_start) FROM fy)),
ranked AS (
    SELECT state_name, fy_start, total_mu,
           ROW_NUMBER() OVER (ORDER BY total_mu DESC) AS rn_desc,
           ROW_NUMBER() OVER (ORDER BY total_mu ASC)  AS rn_asc
    FROM latest
)
SELECT CASE WHEN rn_desc <= 5 THEN 'Top 5' ELSE 'Bottom 5' END AS bucket,
       fy_start, state_name, total_mu
FROM ranked
WHERE rn_desc <= 5 OR rn_asc <= 5
ORDER BY total_mu DESC;
