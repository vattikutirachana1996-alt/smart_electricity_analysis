import pandas as pd
from src import validation as v


def test_duplicates_detected():
    d = pd.DataFrame({"state": ["A", "A", "B"], "period": pd.to_datetime(["2020-04-01"] * 3), "x_mu": [1, 2, 3]})
    assert len(v.duplicate_rows(d)) == 2


def test_missing_report():
    d = pd.DataFrame({"a_mu": [1, None, None, 4]})
    r = v.missing_report(d, ["a_mu"]).iloc[0]
    assert r["missing"] == 2 and r["missing_pct"] == 50.0


def test_range_issues():
    d = pd.DataFrame({"energy_requirement_mu": [-5, 100000], "peak_demand_mw": [100, 100], "peak_met_mw": [200, 90]})
    msgs = " ".join(i["message"] for i in v.range_issues(d))
    assert "negative" in msgs and "peak met exceeds" in msgs and "unit" in msgs


def test_month_gaps():
    d = pd.DataFrame({"state": ["A"] * 3, "period": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-05-01"])})
    assert v.month_gaps(d).iloc[0]["missing_months"] == 2
