import pandas as pd
import pytest
from src import preprocessing as pp
from src.config import ENERGY_TO_MU, POWER_TO_MW


def raw(**kw):
    base = {"State": ["Maharashtra", "Orissa", "Northern Region", "Atlantis"],
            "Month": ["Apr-2022", "2022-04-01", "01/04/2022", "Apr-2022"],
            "Req": ["1,000", "500", "9999", "1"], "Avail": ["990", "-", "9999", "1"]}
    base.update(kw)
    return pd.DataFrame(base)


MAP = {"state": "State", "period": "Month", "energy_requirement_mu": "Req", "energy_availability_mu": "Avail"}


def test_unit_conversion_factors():
    assert ENERGY_TO_MU["GWh"] == 1 and ENERGY_TO_MU["TWh"] == 1000 and ENERGY_TO_MU["MWh"] == pytest.approx(0.001)
    assert POWER_TO_MW["GW"] == 1000


def test_state_standardisation_aggregates_and_unknown():
    r = pp.build_clean(raw(), MAP)
    assert set(r.data["state"]) == {"Maharashtra", "Odisha"}           # alias Orissa -> Odisha
    reasons = set(r.excluded["reason"])
    assert reasons == {"Aggregate row", "Unrecognised state name"}      # nothing dropped silently
    assert any("aggregate" in i["message"].lower() for i in r.issues)


def test_numbers_commas_and_missing():
    r = pp.build_clean(raw(), MAP)
    mh = r.data[r.data["state"] == "Maharashtra"].iloc[0]
    assert mh["energy_requirement_mu"] == 1000 and mh["energy_availability_mu"] == 990
    assert pd.isna(r.data[r.data["state"] == "Odisha"].iloc[0]["energy_availability_mu"])


def test_energy_conversion_twh_to_mu():
    r = pp.build_clean(raw(), MAP, energy_unit="TWh")
    assert r.data[r.data["state"] == "Maharashtra"].iloc[0]["energy_requirement_mu"] == 1_000_000


def test_period_is_first_of_month():
    r = pp.build_clean(raw(), MAP)
    assert (r.data["period"].dt.day == 1).all()


def test_missing_required_mapping_is_error():
    r = pp.build_clean(raw(), {"state": None, "period": "Month", "energy_requirement_mu": "Req"})
    assert r.has_errors


def test_bad_dates_reported_not_dropped_silently():
    r = pp.build_clean(raw(Month=["not a date", "Apr-2022", "Apr-2022", "Apr-2022"]), MAP)
    assert "Unreadable date" in set(r.excluded["reason"])


def test_month_parsing_is_unambiguous():
    s = pd.Series(["2022-04-01", "2022-04", "Apr-2022", "April 2022", "01/04/2022", "2023-01-05", "garbage", None])
    r = pp.parse_month(s)
    assert [x.month for x in r.iloc[:5]] == [4, 4, 4, 4, 4]       # 01/04/2022 is 1 April (day-first)
    assert r.iloc[5] == pd.Timestamp("2023-01-01")                # ISO never swapped to 5 January/1 May
    assert pd.isna(r.iloc[6]) and pd.isna(r.iloc[7])


def test_excel_datetimes_pass_through():
    s = pd.Series(pd.to_datetime(["2021-11-15", "2022-02-03"]))
    assert list(pp.parse_month(s)) == [pd.Timestamp("2021-11-01"), pd.Timestamp("2022-02-01")]


def test_full_month_range_survives_cleaning():
    months = pd.date_range("2014-04-01", periods=24, freq="MS").strftime("%Y-%m-%d")
    df = pd.DataFrame({"State": ["Kerala"] * 24, "Month": months, "Req": range(100, 124)})
    r = pp.build_clean(df, {"state": "State", "period": "Month", "energy_requirement_mu": "Req"})
    assert r.data["period"].nunique() == 24 and r.data["period"].min() == pd.Timestamp("2014-04-01")
