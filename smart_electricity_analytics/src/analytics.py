"""Pandas analytics. All functions are pure (DataFrame in, DataFrame/dict out) so they are unit-testable."""
import numpy as np
import pandas as pd


def add_fiscal_year(df: pd.DataFrame) -> pd.DataFrame:
    """Indian fiscal year runs April-March. fy_start=2019 means FY 2019-20."""
    d = df.copy()
    d["fy_start"] = d["period"].dt.year - (d["period"].dt.month < 4).astype(int)
    d["fy"] = d["fy_start"].astype(str) + "-" + ((d["fy_start"] + 1) % 100).astype(str).str.zfill(2)
    return d


def national_monthly(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Sum across states per month, plus states_reporting so coverage changes are visible."""
    g = df.groupby("period").agg(**{c: (c, "sum") for c in cols}, states_reporting=("state", "nunique"))
    g["coverage_complete"] = g["states_reporting"] == g["states_reporting"].max()
    return g.reset_index()


def with_changes(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Add MoM% and YoY% by matching the exact previous month / same month last year (gaps give NaN)."""
    out = df[["state", "region", "period", col]].dropna(subset=[col]).copy()
    for name, months in (("mom", 1), ("yoy", 12)):
        prev = out[["state", "period", col]].copy()
        prev["period"] = prev["period"] + pd.DateOffset(months=months)
        prev = prev.rename(columns={col: f"prev_{name}"})
        out = out.merge(prev, on=["state", "period"], how="left")
        out[f"{name}_pct"] = np.where(out[f"prev_{name}"] > 0, (out[col] / out[f"prev_{name}"] - 1) * 100, np.nan)
    return out.sort_values(["state", "period"]).reset_index(drop=True)


def moving_average(df: pd.DataFrame, col: str, window: int = 3) -> pd.DataFrame:
    """Calendar-aware moving average: a missing month leaves NaN rather than silently averaging across the gap."""
    wide = df.pivot_table(index="period", columns="state", values=col, aggfunc="sum").asfreq("MS")
    ma = wide.rolling(window, min_periods=window).mean()
    long = ma.stack(future_stack=True).rename(f"ma{window}").reset_index()
    return long.merge(df[["state", "period", col]], on=["state", "period"], how="right")


def fy_totals(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Fiscal-year totals per state, only for complete years (12 reported months)."""
    d = add_fiscal_year(df).dropna(subset=[col])
    g = d.groupby(["state", "region", "fy_start", "fy"]).agg(total=(col, "sum"), n_months=(col, "count")).reset_index()
    g = g[g["n_months"] == 12].copy()
    g = g.sort_values(["state", "fy_start"])
    prev = g.groupby("state")["total"].shift(1)
    contiguous = g.groupby("state")["fy_start"].diff() == 1
    g["yoy_pct"] = np.where(contiguous & (prev > 0), (g["total"] / prev - 1) * 100, np.nan)
    return g.reset_index(drop=True)


def rank_states(fy: pd.DataFrame) -> pd.DataFrame:
    f = fy.copy()
    f["rank_total"] = f.groupby("fy_start")["total"].rank(method="min", ascending=False).astype(int)
    f["rank_growth"] = f.groupby("fy_start")["yoy_pct"].rank(method="min", ascending=False)
    return f


def supply_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Energy shortfall (MU) = requirement - availability; positive = deficit, negative = surplus.
    Peak gap (MW) = peak demand - peak met. Energy (MU) and power (MW) are never mixed."""
    d = df.copy()
    if {"energy_requirement_mu", "energy_availability_mu"} <= set(d.columns):
        d["energy_gap_mu"] = d["energy_requirement_mu"] - d["energy_availability_mu"]
        d["energy_gap_pct"] = np.where(d["energy_requirement_mu"] > 0, d["energy_gap_mu"] / d["energy_requirement_mu"] * 100, np.nan)
    if {"peak_demand_mw", "peak_met_mw"} <= set(d.columns):
        d["peak_gap_mw"] = d["peak_demand_mw"] - d["peak_met_mw"]
        d["peak_gap_pct"] = np.where(d["peak_demand_mw"] > 0, d["peak_gap_mw"] / d["peak_demand_mw"] * 100, np.nan)
    return d


def kpis(df: pd.DataFrame) -> dict:
    """Only metrics whose source columns have data are returned."""
    k = {}
    for c, label in (("energy_requirement_mu", "Total energy requirement (MU)"),
                     ("energy_availability_mu", "Total energy availability (MU)")):
        if c in df and df[c].notna().any():
            k[label] = float(df[c].sum())
    if "Total energy requirement (MU)" in k and "Total energy availability (MU)" in k:
        both = df.dropna(subset=["energy_requirement_mu", "energy_availability_mu"])
        gap = both["energy_requirement_mu"].sum() - both["energy_availability_mu"].sum()
        k["Energy deficit (+) / surplus (-) (MU)"] = float(gap)
        req = both["energy_requirement_mu"].sum()
        k["Deficit / requirement (%)"] = float(gap / req * 100) if req else float("nan")
    # Peaks occur at different times in different states, so they are NOT summed.
    for c, label in (("peak_demand_mw", "Highest single-state peak demand (MW)"),
                     ("peak_met_mw", "Highest single-state peak met (MW)")):
        if c in df and df[c].notna().any():
            k[label] = float(df[c].max())
    return k


def describe(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return (df.groupby("state")[col].describe().round(2).reset_index()
            .rename(columns={"50%": "median", "25%": "q1", "75%": "q3"}))


def seasonal_profile(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Average share of each calendar month in its fiscal-year total (complete years only)."""
    d = add_fiscal_year(df).dropna(subset=[col])
    cnt = d.groupby(["state", "fy_start"])[col].transform("count")
    d = d[cnt == 12].copy()
    d["share_pct"] = d[col] / d.groupby(["state", "fy_start"])[col].transform("sum") * 100
    d["month"] = d["period"].dt.month
    return d.groupby("month")["share_pct"].mean().reset_index()


def linear_trend_estimate(series: pd.Series) -> dict:
    """Simple OLS line on a yearly series. An illustrative estimate, not a forecast model."""
    s = series.dropna()
    if len(s) < 4:
        return {"ok": False, "reason": "Need at least 4 complete years."}
    x = np.arange(len(s))
    slope, intercept = np.polyfit(x, s.values, 1)
    fit = slope * x + intercept
    ss_res, ss_tot = ((s.values - fit) ** 2).sum(), ((s.values - s.values.mean()) ** 2).sum()
    return {"ok": True, "slope_per_year": float(slope), "r2": float(1 - ss_res / ss_tot) if ss_tot else float("nan"), "n_years": len(s)}
