# Data-source register and feature-to-data mapping

> I could not download files in the build environment (no network). Nothing here was fetched
> automatically, and the app ships with **no data**. Verify every URL, period and column against
> the live CEA site before importing; CEA reorganises its portal from time to time.

## Official sources identified

| # | Dataset / report | Where to find it | Publisher | Frequency | Geography | Units | Role in this project |
|---|---|---|---|---|---|---|---|
| 1 | **Monthly Power Supply Position** (appears in CEA's monthly "Executive Summary / Power Sector" dashboard reports as: Requirement, Availability, Peak Demand, Peak Met) | https://cea.nic.in/dashboard/?lang=en -> Reports (Power Supply Position / Executive Summary) | Central Electricity Authority, Ministry of Power | Monthly (provisional and "actual, previous month") | Region and State/UT | Energy: MU; Peak: MW | **Primary dataset** for all pages |
| 2 | **Load Generation Balance Report (LGBR)**, annual - Annexures give month-wise actual power supply position by State/UT for the previous year and anticipated figures | https://cea.nic.in -> Reports -> Annual / LGBR | CEA | Annual report, monthly tables | State/UT | MU, MW | Optional back-fill of earlier years (use **actual** tables only, never "anticipated") |
| 3 | Open-data copy "Energy Requirement and Availability" (state, state code, energy required, energy available, monthly) | India Data Portal / data.gov.in (search the title) | Derived from CEA | Monthly | State | MU | Optional machine-readable alternative; check it states CEA as origin and the coverage period |

Key facts from CEA's own report notes (confirmed from the report text found while researching):
* Both "peak met" and "energy availability" represent **net consumption including transmission losses** in each State.
* Lakshadweep and Andaman & Nicobar are stand-alone systems and are **not part of regional totals**.
* Figures labelled *provisional* may be revised in later months.

Not available from these sources (so not built, and not faked): metered consumption by consumer category,
per-capita consumption, population. Per-capita comparison needs a separate official population source
(e.g. Census/Registrar General projections) and compatible state definitions; it is intentionally absent.

## Feature-to-data mapping

| Feature | Needs | Status |
|---|---|---|
| Energy requirement / availability KPIs, trends, deficit | Dataset 1 or 2 | Implemented |
| Peak demand / peak met, peak gap | Dataset 1 or 2 | Implemented (peaks never summed across states) |
| "Total electricity consumption" | Metered consumption series | **Not supported**; availability shown as a labelled proxy |
| State and region comparison, rankings, growth | Dataset 1 or 2 | Implemented |
| Seasonal comparison | >= 1 complete fiscal year | Implemented (share of annual total by month) |
| Anomaly detection | >= 5 complete fiscal years for each state | Implemented (Z-score, IQR) |
| Per-capita, consumer categories | Extra official datasets | Not implemented |

## Download instructions
1. Open the CEA dashboard link, locate the monthly Power Supply Position report for each month (PDF).
2. Extract the state table to CSV/Excel (Excel "From PDF", Tabula, or manual copy). Keep one row per state per month with columns such as `State, Month, Energy Requirement, Energy Availability, Peak Demand, Peak Met`.
3. Do **not** include region or "All India" rows (the importer excludes and reports them anyway).
4. Record the URL and download date; the Data Management page asks for them and stores them in `data_sources`.
