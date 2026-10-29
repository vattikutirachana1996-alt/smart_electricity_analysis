import numpy as np
import pandas as pd
import pytest
from src import analytics as an
from tests.synthetic_fixtures import make_series


def test_fiscal_year_labels():
    d = pd.DataFrame({"period": pd.to_datetime(["2020-03-01", "2020-04-01"])})
    r = an.add_fiscal_year(d)
    assert list(r["fy"]) == ["2019-20", "2020-21"]


def test_mom_yoy_exact_values():
    d = make_series(years=3)
    ch = an.with_changes(d, "energy_availability_mu")
    row = ch[ch["period"] == pd.Timestamp("2015-05-01")].iloc[0]
    prev = d[d["period"] == pd.Timestamp("2015-04-01")]["energy_availability_mu"].iloc[0]
    assert row["mom_pct"] == pytest.approx((row["energy_availability_mu"] / prev - 1) * 100)
    assert ch["yoy_pct"].isna().sum() == 12          # first year has no prior year


def test_mom_gap_gives_nan_not_wrong_value():
    d = make_series(years=2)
    d = d[d["period"] != pd.Timestamp("2014-06-01")]
    ch = an.with_changes(d, "energy_availability_mu")
    assert pd.isna(ch[ch["period"] == pd.Timestamp("2014-07-01")]["mom_pct"].iloc[0])


def test_moving_average_respects_gaps():
    d = make_series(years=2)
    d = d[d["period"] != pd.Timestamp("2014-06-01")]
    ma = an.moving_average(d, "energy_availability_mu", 3)
    assert pd.isna(ma[ma["period"] == pd.Timestamp("2014-07-01")]["ma3"].iloc[0])
    ok = ma[ma["period"] == pd.Timestamp("2014-10-01")]["ma3"].iloc[0]
    exp = d[d["period"].isin(pd.to_datetime(["2014-08-01", "2014-09-01", "2014-10-01"]))]["energy_availability_mu"].mean()
    assert ok == pytest.approx(exp)


def test_fy_totals_only_complete_years():
    d = make_series(years=3)
    d = d[d["period"] < pd.Timestamp("2017-01-01")]        # last FY incomplete
    fy = an.fy_totals(d, "energy_availability_mu")
    assert list(fy["fy_start"]) == [2014, 2015]


def test_supply_gap_formulas_and_sign():
    d = pd.DataFrame({"energy_requirement_mu": [100.0], "energy_availability_mu": [95.0],
                      "peak_demand_mw": [200.0], "peak_met_mw": [210.0]})
    r = an.supply_gap(d).iloc[0]
    assert r["energy_gap_mu"] == 5 and r["energy_gap_pct"] == 5.0
    assert r["peak_gap_mw"] == -10                         # surplus is negative


def test_kpis_never_sum_peaks_and_skip_missing():
    d = pd.concat([make_series("A", base=100), make_series("B", base=200)])
    k = an.kpis(d)
    assert k["Highest single-state peak demand (MW)"] == d["peak_demand_mw"].max()
    assert "Energy deficit (+) / surplus (-) (MU)" in k
    k2 = an.kpis(d.drop(columns=["energy_requirement_mu"]))
    assert "Total energy requirement (MU)" not in k2 and "Deficit / requirement (%)" not in k2


def test_linear_trend_needs_enough_data():
    assert not an.linear_trend_estimate(pd.Series([1, 2, 3]))["ok"]
    e = an.linear_trend_estimate(pd.Series([10, 20, 30, 40, 50]))
    assert e["slope_per_year"] == pytest.approx(10) and e["r2"] == pytest.approx(1)
