-- name: q01_null_counts
-- title: NULL counts per metric column
-- feature: Data quality
SELECT COUNT(*) AS total_rows,
       SUM(energy_requirement_mu  IS NULL) AS null_requirement,
       SUM(energy_availability_mu IS NULL) AS null_availability,
       SUM(peak_demand_mw IS NULL)         AS null_peak_demand,
       SUM(peak_met_mw    IS NULL)         AS null_peak_met
FROM power_supply_monthly;

-- name: q02_duplicate_keys
-- title: Duplicate (state, month) keys (should be zero; also enforced by a UNIQUE constraint)
-- feature: Data quality
SELECT state_id, period_month, COUNT(*) AS copies
FROM power_supply_monthly
GROUP BY state_id, period_month
HAVING COUNT(*) > 1;

-- name: q03_peak_met_exceeds_demand
-- title: Rows where peak met is greater than peak demand
-- feature: Data quality
SELECT st.state_name, p.period_month, p.peak_demand_mw, p.peak_met_mw
FROM power_supply_monthly p
JOIN states st ON st.state_id = p.state_id
WHERE p.peak_met_mw > p.peak_demand_mw * 1.001
ORDER BY p.period_month, st.state_name;

-- name: q04_missing_month_gaps
-- title: Gaps in each state's monthly series (LAG)
-- feature: Data quality, LAG
WITH g AS (
    SELECT st.state_name, p.period_month,
           LAG(p.period_month) OVER (PARTITION BY st.state_name ORDER BY p.period_month) AS prev_month
    FROM power_supply_monthly p
    JOIN states st ON st.state_id = p.state_id
)
SELECT state_name, prev_month, period_month,
       TIMESTAMPDIFF(MONTH, prev_month, period_month) - 1 AS months_missing_between
FROM g
WHERE prev_month IS NOT NULL AND TIMESTAMPDIFF(MONTH, prev_month, period_month) > 1
ORDER BY state_name, period_month;

-- name: q05_state_coverage_by_month
-- title: Number of states reporting in each month (coverage changes distort national totals)
-- feature: Data quality
SELECT period_month, COUNT(DISTINCT state_id) AS states_reporting
FROM power_supply_monthly
GROUP BY period_month
ORDER BY period_month;

-- name: q06_zero_or_negative_values
-- title: Zero or negative values
-- feature: Data quality
SELECT st.state_name, p.period_month, p.energy_requirement_mu, p.energy_availability_mu, p.peak_demand_mw, p.peak_met_mw
FROM power_supply_monthly p
JOIN states st ON st.state_id = p.state_id
WHERE p.energy_requirement_mu <= 0 OR p.energy_availability_mu <= 0 OR p.peak_demand_mw <= 0 OR p.peak_met_mw <= 0;
