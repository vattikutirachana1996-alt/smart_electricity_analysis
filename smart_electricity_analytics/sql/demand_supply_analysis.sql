-- Energy (MU) and peak power (MW) are analysed separately and never added together.

-- name: d01_fy_requirement_vs_availability
-- title: National requirement vs availability per fiscal year (complete state-years only)
-- feature: CTE, aggregation
WITH fy_state AS (
    SELECT p.state_id,
           CASE WHEN MONTH(p.period_month) >= 4 THEN YEAR(p.period_month) ELSE YEAR(p.period_month) - 1 END AS fy_start,
           SUM(p.energy_requirement_mu)  AS req_mu,
           SUM(p.energy_availability_mu) AS avail_mu
    FROM power_supply_monthly p
    GROUP BY p.state_id, fy_start
    HAVING COUNT(p.energy_requirement_mu) = 12 AND COUNT(p.energy_availability_mu) = 12
)
SELECT fy_start, COUNT(*) AS states_complete,
       ROUND(SUM(req_mu), 0) AS requirement_mu, ROUND(SUM(avail_mu), 0) AS availability_mu,
       ROUND(SUM(req_mu) - SUM(avail_mu), 0) AS deficit_mu,
       ROUND(100 * (SUM(req_mu) - SUM(avail_mu)) / NULLIF(SUM(req_mu), 0), 2) AS deficit_pct
FROM fy_state
GROUP BY fy_start
ORDER BY fy_start;

-- name: d02_state_cumulative_deficit_rank
-- title: States ranked by cumulative energy shortfall over the loaded period
-- feature: RANK
WITH g AS (
    SELECT st.state_name,
           SUM(p.energy_requirement_mu - p.energy_availability_mu) AS shortfall_mu,
           SUM(p.energy_requirement_mu) AS requirement_mu
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.energy_requirement_mu IS NOT NULL AND p.energy_availability_mu IS NOT NULL
    GROUP BY st.state_name
)
SELECT state_name, ROUND(shortfall_mu, 1) AS shortfall_mu,
       ROUND(100 * shortfall_mu / NULLIF(requirement_mu, 0), 3) AS shortfall_pct,
       RANK() OVER (ORDER BY shortfall_mu DESC) AS shortfall_rank
FROM g
ORDER BY shortfall_rank;

-- name: d03_largest_monthly_shortfalls
-- title: 20 largest state-month energy shortfalls
-- feature: Window ranking
SELECT * FROM (
    SELECT st.state_name, p.period_month,
           p.energy_requirement_mu, p.energy_availability_mu,
           ROUND(p.energy_requirement_mu - p.energy_availability_mu, 2) AS shortfall_mu,
           ROUND(100 * (p.energy_requirement_mu - p.energy_availability_mu) / NULLIF(p.energy_requirement_mu, 0), 2) AS shortfall_pct,
           DENSE_RANK() OVER (ORDER BY (p.energy_requirement_mu - p.energy_availability_mu) DESC) AS rnk
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.energy_requirement_mu IS NOT NULL AND p.energy_availability_mu IS NOT NULL
) t
WHERE rnk <= 20
ORDER BY rnk;

-- name: d04_peak_demand_vs_met
-- title: Peak demand vs peak met, with previous-month peak demand (LAG)
-- feature: LAG
SELECT st.state_name, p.period_month, p.peak_demand_mw, p.peak_met_mw,
       ROUND(p.peak_demand_mw - p.peak_met_mw, 1) AS peak_gap_mw,
       ROUND(100 * (p.peak_demand_mw - p.peak_met_mw) / NULLIF(p.peak_demand_mw, 0), 2) AS peak_gap_pct,
       LAG(p.peak_demand_mw) OVER (PARTITION BY st.state_name ORDER BY p.period_month) AS prev_row_peak_demand_mw
FROM power_supply_monthly p
JOIN states st ON st.state_id = p.state_id
WHERE p.peak_demand_mw IS NOT NULL AND p.peak_met_mw IS NOT NULL
ORDER BY st.state_name, p.period_month;

-- name: d05_requirement_growth_fy
-- title: Fiscal-year energy requirement growth per state
-- feature: LAG over fiscal years
WITH fy AS (
    SELECT st.state_name,
           CASE WHEN MONTH(p.period_month) >= 4 THEN YEAR(p.period_month) ELSE YEAR(p.period_month) - 1 END AS fy_start,
           SUM(p.energy_requirement_mu) AS req_mu
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    GROUP BY st.state_name, fy_start
    HAVING COUNT(p.energy_requirement_mu) = 12
)
SELECT state_name, fy_start, ROUND(req_mu, 0) AS requirement_mu,
       ROUND(100 * (req_mu - LAG(req_mu) OVER w) / NULLIF(LAG(req_mu) OVER w, 0), 2) AS growth_pct,
       fy_start - LAG(fy_start) OVER w AS years_gap_check
FROM fy
WINDOW w AS (PARTITION BY state_name ORDER BY fy_start)
ORDER BY state_name, fy_start;

-- name: d06_highest_peak_per_state
-- title: Highest recorded peak demand per state with month (DENSE_RANK)
-- feature: DENSE_RANK in a CTE
WITH r AS (
    SELECT st.state_name, p.period_month, p.peak_demand_mw, p.peak_met_mw,
           DENSE_RANK() OVER (PARTITION BY st.state_name ORDER BY p.peak_demand_mw DESC) AS rk
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
    WHERE p.peak_demand_mw IS NOT NULL
)
SELECT state_name, period_month, peak_demand_mw, peak_met_mw
FROM r WHERE rk = 1
ORDER BY peak_demand_mw DESC;
