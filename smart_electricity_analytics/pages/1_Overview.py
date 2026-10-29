import pandas as pd
import plotly.express as px
import streamlit as st
from src import ui, analytics as an, anomaly_detection as ad
from src.config import AVAILABILITY_NOTE, METRICS

ui.setup("Executive Overview", "📊")
raw = ui.get_data()
df = ui.sidebar_filters(raw)

k = an.kpis(df)
if not k:
    st.info("The imported data has no energy or peak columns yet.")
cols = st.columns(3)
for i, (label, val) in enumerate(k.items()):
    unit = "%" if "(%)" in label else ""
    cols[i % 3].metric(label, ui.fmt(val, unit))

# anomaly count on the full (unfiltered by date) series of the chosen state/region selection
metric_for_anom = next((m for m in ("energy_availability_mu", "energy_requirement_mu") if df[m].notna().any()), None)
if metric_for_anom:
    _, flagged, info = ad.detect_anomalies(df, metric_for_anom, "zscore", 2.5)
    cols[len(k) % 3].metric("Anomalies flagged (|z| >= 2.5)", f"{len(flagged):,}",
                            help="Statistical signals needing investigation, not proof of faults or theft.")
st.caption("Peak values are the highest single-state figure, not a sum: states peak at different times, so summed peaks would overstate national demand.")

en = ui.available_metrics(df, ["energy_requirement_mu", "energy_availability_mu"])
if en:
    nat = an.national_monthly(df, list(en))
    if not nat["coverage_complete"].all():
        st.warning("The number of reporting states changes between months, so the national trend can jump for "
                   "coverage reasons. See the coverage line below.")
    long = nat.melt("period", list(en), var_name="metric", value_name="MU")
    long["metric"] = long["metric"].map(en)
    st.plotly_chart(ui.line(long, "period", "MU", "metric", "National monthly energy (sum of reporting states)", "MU"),
                    use_container_width=True)
    with st.expander("States reporting per month"):
        st.plotly_chart(px.bar(nat, x="period", y="states_reporting"), use_container_width=True)

left, right = st.columns(2)
metric = "energy_availability_mu" if "energy_availability_mu" in en else (list(en)[0] if en else None)
if metric:
    fy = an.fy_totals(df, metric)
    with left:
        if fy.empty:
            st.info("State comparison needs at least one complete fiscal year (12 months) in the filtered range.")
        else:
            last = fy[fy["fy_start"] == fy["fy_start"].max()].sort_values("total", ascending=False).head(15)
            st.plotly_chart(px.bar(last, x="total", y="state", orientation="h", color="region",
                                   title=f"Top states, FY {last['fy'].iloc[0]} - {METRICS[metric]}",
                                   color_discrete_sequence=ui.PALETTE).update_layout(yaxis={"categoryorder": "total ascending"}),
                            use_container_width=True)
    with right:
        nat_fy = fy.groupby(["fy_start", "fy"]).agg(total=("total", "sum"), states=("state", "nunique")).reset_index()
        if len(nat_fy) >= 2:
            nat_fy["yoy_pct"] = nat_fy["total"].pct_change() * 100
            nat_fy.loc[nat_fy["states"] != nat_fy["states"].shift(1), "yoy_pct"] = float("nan")
            st.plotly_chart(px.bar(nat_fy, x="fy", y="yoy_pct", title="Year-on-year growth (fiscal year, %)",
                                   color_discrete_sequence=[ui.PALETTE[0]]), use_container_width=True)
            st.caption("YoY is shown only when the same number of states is present in both years.")
        else:
            st.info("Year-on-year growth needs at least two complete fiscal years.")
st.caption(f"Last reporting period in view: **{df['period'].max():%B %Y}**. {AVAILABILITY_NOTE}")
ui.source_panel()
