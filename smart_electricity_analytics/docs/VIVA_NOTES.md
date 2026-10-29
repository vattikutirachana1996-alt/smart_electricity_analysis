# Viva notes (one paragraph per module)

* **config.py** - fixed constants: unit factors (1 MU = 1 GWh), metric names. One place to change units.
* **preprocessing.py** - turns any uploaded table into `(state, region, month, 4 metrics)`. Standardises state names (alias table), removes
  region/All-India rows to avoid double counting, converts units to MU/MW, reports every excluded row.
* **validation.py** - missing-value %, duplicate (state, month), negative/implausible values (unit-mistake heuristics), month gaps.
* **database.py** - SQLAlchemy engine from `.env`; imports in one transaction (all-or-nothing); duplicates are skipped or overwritten only by explicit choice; parses `sql/*.sql` for the SQL page.
* **analytics.py** - fiscal year (Apr-Mar), MoM/YoY by exact-month matching, gap-aware moving average, complete-year totals, shortfall formulas, KPIs (peaks not summed).
* **anomaly_detection.py** - ratio to fiscal-year mean, then Z-score or IQR within state + calendar month.
* **ui.py / pages** - Streamlit layout, filters, charts, exports.
* **sql/** - schema and 22 queries: CTE, LAG, RANK/DENSE_RANK/ROW_NUMBER, 3-month window frame, running total, YoY self-join, multi-table join, data-quality checks.

Likely questions: Why not machine learning? (brief forbids it; statistics are explainable.) Why is availability not consumption? (CEA definition, includes losses.)
Why not sum peaks? (non-coincident.) Why complete fiscal years only? (partial years bias totals.) Why can z never reach 3 with 5 years? (bound (n-1)/sqrt(n).)
