"""SYNTHETIC test data. NOT official CEA data. Used only by automated tests; never loaded by the app."""
import numpy as np
import pandas as pd

SEASON = np.array([1.00, 1.05, 1.10, 1.15, 1.12, 1.05, 0.98, 0.95, 0.95, 0.92, 0.90, 0.95])  # Apr..Mar shape


def make_series(state="Testland", base=1000.0, years=8, start_fy=2014, growth=0.05, seed=0, spike=None):
    """Monthly series Apr..Mar for `years` fiscal years. spike=(fy_index, month_index, multiplier)."""
    rng = np.random.default_rng(seed)
    rows = []
    for y in range(years):
        for m in range(12):
            period = pd.Timestamp(start_fy + y + (1 if m >= 9 else 0), (m + 3) % 12 + 1, 1)
            v = base * (1 + growth) ** y * SEASON[m] * (1 + rng.normal(0, 0.01))
            if spike and spike[0] == y and spike[1] == m:
                v *= spike[2]
            rows.append((state, "Northern", period, v, v * 1.01, v / 700, v / 720))
    return pd.DataFrame(rows, columns=["state", "region", "period", "energy_requirement_mu",
                                       "energy_availability_mu", "peak_demand_mw", "peak_met_mw"])
