from types import SimpleNamespace

import pandas as pd
import pytest

from src import ui


def test_sidebar_date_range_includes_month_for_any_day_in_that_month(monkeypatch):
    selected_range = (pd.Timestamp("2024-04-15").date(), pd.Timestamp("2024-04-30").date())
    calls = {}

    def date_input(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return selected_range

    sidebar = SimpleNamespace(
        header=lambda *args, **kwargs: None,
        multiselect=lambda *args, **kwargs: [],
        button=lambda *args, **kwargs: False,
        date_input=date_input,
    )
    fake_streamlit = SimpleNamespace(sidebar=sidebar, session_state={}, info=lambda *args, **kwargs: None)
    monkeypatch.setattr(ui, "st", fake_streamlit)

    data = pd.DataFrame({
        "region": ["Northern"],
        "state": ["Delhi"],
        "period": pd.to_datetime(["2024-04-01"]),
    })
    filtered = ui.sidebar_filters(data)

    assert calls["args"][1] == (pd.Timestamp("2024-04-01").date(), pd.Timestamp("2024-04-01").date())
    assert "min_value" not in calls["kwargs"]
    assert "max_value" not in calls["kwargs"]
    assert calls["kwargs"]["key"] == "date_range_2024-04-01_2024-04-01"
    assert "monthly" in calls["kwargs"]["help"].lower()
    assert filtered.equals(data)


def test_sidebar_date_range_explains_when_selected_period_has_no_data(monkeypatch):
    messages = []

    class StopApp(Exception):
        pass

    def stop():
        raise StopApp()

    sidebar = SimpleNamespace(
        header=lambda *args, **kwargs: None,
        multiselect=lambda *args, **kwargs: [],
        button=lambda *args, **kwargs: False,
        date_input=lambda *args, **kwargs: (
            pd.Timestamp("2024-05-01").date(),
            pd.Timestamp("2024-05-31").date(),
        ),
    )
    fake_streamlit = SimpleNamespace(
        sidebar=sidebar,
        info=lambda message, *args, **kwargs: messages.append(message),
        stop=stop,
    )
    monkeypatch.setattr(ui, "st", fake_streamlit)
    data = pd.DataFrame({
        "region": ["Northern"],
        "state": ["Delhi"],
        "period": pd.to_datetime(["2024-04-01"]),
    })

    with pytest.raises(StopApp):
        ui.sidebar_filters(data)

    assert "Apr 2024" in messages[0]
    assert "import data" in messages[0]


def test_reset_date_range_clears_saved_month_filter(monkeypatch):
    date_key = "date_range_2019-04-01_2024-04-01"
    saved_range = (pd.Timestamp("2024-04-01").date(), pd.Timestamp("2024-04-30").date())
    session_state = {date_key: saved_range}
    calls = {}

    def date_input(label, value, **kwargs):
        calls["value"] = value
        calls["key"] = kwargs["key"]
        return value

    sidebar = SimpleNamespace(
        header=lambda *args, **kwargs: None,
        multiselect=lambda *args, **kwargs: [],
        button=lambda label: label == "Reset date range to all available data",
        date_input=date_input,
    )
    fake_streamlit = SimpleNamespace(
        sidebar=sidebar,
        session_state=session_state,
        info=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(ui, "st", fake_streamlit)
    data = pd.DataFrame({
        "region": ["Western", "Western"],
        "state": ["Maharashtra", "Maharashtra"],
        "period": pd.to_datetime(["2019-04-01", "2024-04-01"]),
    })

    filtered = ui.sidebar_filters(data)

    assert date_key not in session_state
    assert calls["key"] == date_key
    assert calls["value"] == (pd.Timestamp("2019-04-01").date(), pd.Timestamp("2024-04-01").date())
    assert len(filtered) == 2


def test_source_panel_is_expanded_and_displays_registered_source(monkeypatch):
    shown = {}
    source = pd.DataFrame({
        "dataset_name": ["Demo"],
        "publisher": ["Synthetic demo data (not official)"],
        "period_start": ["2019-04-01"],
        "period_end": ["2024-03-01"],
    })

    class Expander:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def expander(label, **kwargs):
        shown["label"] = label
        shown["expanded"] = kwargs.get("expanded")
        return Expander()

    fake_streamlit = SimpleNamespace(
        expander=expander,
        dataframe=lambda data, **kwargs: shown.update(data=data),
        warning=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(ui, "st", fake_streamlit)
    monkeypatch.setattr(ui, "_sources", lambda: source)

    ui.source_panel()

    assert shown["expanded"] is True
    assert shown["label"] == "Data source and reporting period"
    assert shown["data"].equals(source)


def test_source_panel_explains_when_no_sources_are_registered(monkeypatch):
    messages = []

    class Expander:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(ui, "_sources", lambda: pd.DataFrame())
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: Expander())
    monkeypatch.setattr(ui.st, "info", lambda message, *args, **kwargs: messages.append(message))

    ui.source_panel()

    assert messages == ["No data sources have been registered yet. Import a dataset from Data Management."]


def test_line_plot_can_show_a_single_month_as_a_marker():
    figure = ui.line(
        pd.DataFrame({"period": pd.to_datetime(["2024-04-01"]), "value": [10]}),
        "period",
        "value",
        markers=True,
    )

    assert "markers" in figure.data[0].mode


def test_high_usage_warning_identifies_latest_high_anomaly(monkeypatch):
    messages = []
    monkeypatch.setattr(ui.st, "warning", lambda message: messages.append(message))
    flagged = pd.DataFrame({
        "state": ["Alpha", "Beta"],
        "period": pd.to_datetime(["2024-04-01", "2024-05-01"]),
        "direction": ["High", "High"],
        "deviation_pct": [35.0, 42.5],
    })

    ui.high_usage_warning(flagged)

    assert len(messages) == 1
    assert "2 state-month record(s)" in messages[0]
    assert "Beta in May 2024" in messages[0]
    assert "42.5% above" in messages[0]


def test_high_usage_warning_ignores_low_anomalies(monkeypatch):
    messages = []
    monkeypatch.setattr(ui.st, "warning", lambda message: messages.append(message))
    flagged = pd.DataFrame({
        "state": ["Alpha"],
        "period": pd.to_datetime(["2024-04-01"]),
        "direction": ["Low"],
        "deviation_pct": [-35.0],
    })

    ui.high_usage_warning(flagged)

    assert messages == []
