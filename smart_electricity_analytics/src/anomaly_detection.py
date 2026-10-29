"""Statistical anomaly detection (no machine learning).

Why not a plain Z-score on raw values?  States differ by orders of magnitude, and every state has
strong seasonality and growth. So we first remove scale and trend:

    ratio = value / mean of that state's fiscal-year (Apr-Mar, complete years only)

Each ratio is then compared with the ratios of the SAME state in the SAME calendar month in other
years (e.g. Maharashtra's Aprils). A flag therefore means "unusual shape for this state and month",
not "large state".
"""
import numpy as np
import pandas as pd
from .analytics import add_fiscal_year


def detect_anomalies(df: pd.DataFrame, metric: str, method: str = "zscore",
                     threshold: float = 2.5, min_group: int = 5):
    """Returns (scored, flagged, info). method: 'zscore' (|z| >= threshold) or 'iqr' (k = threshold)."""
    info = {"rows_input": int(len(df)), "rows_used": 0, "rows_skipped_incomplete_fy": 0,
            "groups_evaluated": 0, "groups_too_small": 0, "max_possible_z": None}
    d = add_fiscal_year(df.dropna(subset=[metric])[["state", "region", "period", metric]].copy())
    cnt = d.groupby(["state", "fy_start"])[metric].transform("count")
    info["rows_skipped_incomplete_fy"] = int((cnt != 12).sum())
    d = d[cnt == 12].copy()
    d["fy_mean"] = d.groupby(["state", "fy_start"])[metric].transform("mean")
    d = d[d["fy_mean"] > 0].copy()
    d["ratio"] = d[metric] / d["fy_mean"]
    d["month"] = d["period"].dt.month
    g = d.groupby(["state", "month"])["ratio"]
    d["n_group"] = g.transform("count")
    d = d[d["n_group"] >= min_group].copy()
    info["rows_used"] = int(len(d))
    info["groups_evaluated"] = int(d.groupby(["state", "month"]).ngroups)
    if d.empty:
        return d, d, info
    g = d.groupby(["state", "month"])["ratio"]
    d["group_mean"] = g.transform("mean")
    if method == "zscore":
        sd = g.transform("std")
        d["score"] = np.where(sd > 0, (d["ratio"] - d["group_mean"]) / sd, 0.0)
        d["is_anomaly"] = d["score"].abs() >= threshold
        info["max_possible_z"] = float((d["n_group"].min() - 1) / np.sqrt(d["n_group"].min()))
        label = f"Z-score (|z| >= {threshold})"
    elif method == "iqr":
        q1, q3 = g.transform(lambda s: s.quantile(.25)), g.transform(lambda s: s.quantile(.75))
        iqr = q3 - q1
        lo, hi = q1 - threshold * iqr, q3 + threshold * iqr
        d["score"] = np.where(d["ratio"] > hi, (d["ratio"] - hi) / iqr.replace(0, np.nan),
                      np.where(d["ratio"] < lo, (d["ratio"] - lo) / iqr.replace(0, np.nan), 0.0))
        d["is_anomaly"] = (d["ratio"] > hi) | (d["ratio"] < lo)
        label = f"IQR (k = {threshold})"
    else:
        raise ValueError("method must be 'zscore' or 'iqr'")
    d["observed"] = d[metric]
    d["baseline"] = d["fy_mean"] * d["group_mean"]       # expected value for this state/month/year
    d["deviation"] = d["observed"] - d["baseline"]
    d["deviation_pct"] = d["deviation"] / d["baseline"] * 100
    d["direction"] = np.where(d["deviation"] >= 0, "High", "Low")
    d["method"] = label
    cols = ["state", "region", "period", "observed", "baseline", "deviation", "deviation_pct",
            "score", "direction", "method", "is_anomaly"]
    scored = d[cols].sort_values(["state", "period"]).reset_index(drop=True)
    flagged = scored[scored["is_anomaly"]].sort_values("score", key=abs, ascending=False).reset_index(drop=True)
    return scored, flagged, info
