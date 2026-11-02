import pandas as pd

from src import analytics, preprocessing
from src.anomaly_detection import detect_anomalies
from src.config import ENERGY_METRICS, POWER_METRICS, ROOT


def test_synthetic_demo_csv_cleans_and_supports_dashboard_analytics():
    path = ROOT / "data" / "demo" / "SYNTHETIC_demo_monthly_power_supply.csv"
    raw = pd.read_csv(path)
    mapping = preprocessing.guess_mapping(raw.columns)
    result = preprocessing.build_clean(raw, mapping)

    assert not result.has_errors
    assert len(result.data) == 600
    assert result.data["state"].nunique() == 10
    assert result.data["period"].nunique() == 60
    assert result.data["period"].min() == pd.Timestamp("2019-04-01")
    assert result.data["period"].max() == pd.Timestamp("2024-03-01")
    assert not result.data.duplicated(["state", "period"]).any()
    assert result.data[ENERGY_METRICS + POWER_METRICS].notna().all().all()
    assert (result.data["energy_availability_mu"] <= result.data["energy_requirement_mu"]).all()
    assert raw["data_type"].eq("SYNTHETIC - NOT OFFICIAL").all()

    fiscal_years = analytics.fy_totals(result.data, "energy_availability_mu")
    assert len(fiscal_years) == 50
    assert fiscal_years["fy"].nunique() == 5
    assert not analytics.with_changes(result.data, "energy_availability_mu")["yoy_pct"].isna().all()
    scored, _, info = detect_anomalies(result.data, "energy_availability_mu")
    assert len(scored) == 600
    assert info["groups_evaluated"] == 120
