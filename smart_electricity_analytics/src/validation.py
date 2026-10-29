"""Validation reports for a cleaned upload. All checks report; none silently modify data."""
import pandas as pd

KEY = ["state", "period"]
# Heuristic plausibility ceilings used only to WARN about possible unit mistakes.
MAX_STATE_MONTH_MU = 30000
MAX_STATE_PEAK_MW = 40000


def missing_report(df: pd.DataFrame, cols) -> pd.DataFrame:
    rows = [(c, int(df[c].isna().sum()), round(100 * df[c].isna().mean(), 2) if len(df) else 0.0) for c in cols]
    return pd.DataFrame(rows, columns=["column", "missing", "missing_pct"])


def duplicate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """All rows that share (state, period) with another row in the same file."""
    return df[df.duplicated(KEY, keep=False)].sort_values(KEY)


def range_issues(df: pd.DataFrame) -> list:
    out = []
    for c in [c for c in df.columns if c.endswith("_mu") or c.endswith("_mw")]:
        n = int((df[c] < 0).sum())
        if n:
            out.append({"level": "error", "message": f"{n} negative value(s) in {c}."})
    if {"peak_demand_mw", "peak_met_mw"} <= set(df.columns):
        n = int((df["peak_met_mw"] > df["peak_demand_mw"] * 1.001).sum())
        if n:
            out.append({"level": "warning", "message": f"{n} row(s) where peak met exceeds peak demand."})
    for c in [c for c in df.columns if c.endswith("_mu")]:
        n = int((df[c] > MAX_STATE_MONTH_MU).sum())
        if n:
            out.append({"level": "warning", "message": f"{n} value(s) in {c} exceed {MAX_STATE_MONTH_MU} MU/month - check the energy unit."})
    for c in [c for c in df.columns if c.endswith("_mw")]:
        n = int((df[c] > MAX_STATE_PEAK_MW).sum())
        if n:
            out.append({"level": "warning", "message": f"{n} value(s) in {c} exceed {MAX_STATE_PEAK_MW} MW - check the power unit."})
    return out


def month_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Missing calendar months inside each state's reported range."""
    rows = []
    for st, g in df.groupby("state"):
        full = pd.date_range(g["period"].min(), g["period"].max(), freq="MS")
        miss = full.difference(pd.DatetimeIndex(g["period"].unique()))
        if len(miss):
            rows.append((st, len(miss), ", ".join(m.strftime("%b %Y") for m in miss[:6]) + (" ..." if len(miss) > 6 else "")))
    return pd.DataFrame(rows, columns=["state", "missing_months", "examples"])
