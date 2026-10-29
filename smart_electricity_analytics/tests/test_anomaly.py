import pandas as pd
import pytest
from src.anomaly_detection import detect_anomalies
from tests.synthetic_fixtures import make_series

M = "energy_availability_mu"


def test_injected_spike_is_found_with_zscore():
    d = make_series(spike=(4, 3, 1.6))                    # +60% in month index 3 of FY index 4
    _, flagged, _ = detect_anomalies(d, M, "zscore", 2.0)
    assert len(flagged) >= 1
    top = flagged.iloc[0]
    assert top["period"] == pd.Timestamp("2018-07-01") and top["direction"] == "High"
    assert top["deviation_pct"] > 40 and top["baseline"] < top["observed"]


def test_injected_drop_is_found_with_iqr():
    d = make_series(spike=(3, 6, 0.5))
    _, flagged, _ = detect_anomalies(d, M, "iqr", 1.5)
    assert ((flagged["period"] == pd.Timestamp("2017-10-01")) & (flagged["direction"] == "Low")).any()


def test_clean_seasonal_growing_series_has_few_flags():
    scored, flagged, _ = detect_anomalies(make_series(), M, "zscore", 2.5)
    assert len(flagged) == 0 and len(scored) == 96        # seasonality and growth are not flagged


def test_scale_independence():
    big = make_series("Big", base=100000)
    small = make_series("Small", base=10, spike=(4, 3, 1.6))
    _, flagged, _ = detect_anomalies(pd.concat([big, small]), M, "zscore", 2.0)
    assert set(flagged["state"]) == {"Small"}


def test_threshold_monotonic():
    d = make_series(spike=(4, 3, 1.3), seed=3)
    n = [len(detect_anomalies(d, M, "zscore", t)[1]) for t in (1.0, 1.5, 2.0, 2.5)]
    assert n == sorted(n, reverse=True)


def test_incomplete_fiscal_year_is_skipped_and_reported():
    d = make_series()
    d = d[d["period"] < pd.Timestamp("2022-01-01")]
    scored, _, info = detect_anomalies(d, M, "zscore", 2.0)
    assert info["rows_skipped_incomplete_fy"] > 0


def test_too_few_years_returns_empty_not_crash():
    scored, flagged, _ = detect_anomalies(make_series(years=3), M, "zscore", 2.0)
    assert scored.empty and flagged.empty


def test_bad_method():
    with pytest.raises(ValueError):
        detect_anomalies(make_series(), M, "magic")
