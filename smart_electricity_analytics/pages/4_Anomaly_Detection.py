import plotly.graph_objects as go
import streamlit as st
from src import ui, anomaly_detection as ad

ui.setup("Statistical Anomaly Detection", "🚨", "Z-score and IQR on scale- and trend-adjusted values (no machine learning)")
raw = ui.get_data()
df = ui.sidebar_filters(raw)
avail = ui.available_metrics(df)
metric = st.selectbox("Metric", list(avail), format_func=avail.get)

c1, c2, c3 = st.columns(3)
method = c1.radio("Method", ["zscore", "iqr"], format_func=lambda m: "Z-score" if m == "zscore" else "IQR (Tukey fences)")
default = 1.5
threshold = c2.slider(
    "Threshold" + (" (|z|)" if method == "zscore" else " (IQR multiplier k)"),
    1.0,
    4.0,
    default,
    0.1,
    help=(
        "The default Z-score threshold is 1.5 so it can be reached with five years of data. "
        "With five observations per month, the maximum possible |z| is about 1.79."
        if method == "zscore" else None
    ),
)
min_group = c3.slider("Min. years per state-month group", 4, 10, 5)

with st.spinner("Computing anomalies..."):
    scored, flagged, info = ad.detect_anomalies(df, metric, method, threshold, min_group)

with st.expander("How the detection works", expanded=False):
    st.markdown("""
- Each value is divided by its **state's fiscal-year mean** (April-March), which removes the state's size and its growth trend.
- That ratio is compared with the ratios for the **same state and same calendar month** in other years, so seasonality
  (e.g. high summer demand) is not flagged and large states are not compared with small ones.
- **Z-score** flags |z| >= threshold. **IQR** flags values beyond Q1 - k*IQR or Q3 + k*IQR (k = 1.5 is the usual convention).
- Only complete fiscal years (12 months) and groups with enough years are evaluated.
""")
if scored.empty:
    st.info("Not enough data: detection needs several complete fiscal years (at least the chosen minimum) for each state.")
    st.caption(f"Rows skipped because their fiscal year is incomplete: {info['rows_skipped_incomplete_fy']}")
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Records evaluated", f"{info['rows_used']:,}")
m2.metric("Anomalies flagged", f"{len(flagged):,}")
m3.metric("Share flagged", f"{100*len(flagged)/max(info['rows_used'],1):.1f}%")
if method == "zscore" and info["max_possible_z"] and threshold > info["max_possible_z"]:
    st.warning(f"With the smallest group size ({min_group}), a |z| above {info['max_possible_z']:.2f} is mathematically impossible. "
               "Lower the threshold or use more years.")
if info["rows_skipped_incomplete_fy"]:
    st.caption(f"{info['rows_skipped_incomplete_fy']} rows were not evaluated because their fiscal year has fewer than 12 months.")

st.info("An anomaly is a **statistical signal that deserves investigation**. It is not evidence of electricity theft, "
        "meter failure or data error; real events (weather, outages, reporting revisions, policy changes) also cause outliers.")

st.subheader("Flagged records")
show = flagged.copy()
show["period"] = show["period"].dt.strftime("%b %Y")
st.dataframe(ui.round2(show[["state", "region", "period", "observed", "baseline", "deviation", "deviation_pct", "score", "direction", "method"]]),
             hide_index=True, use_container_width=True)
ui.download_button(flagged.drop(columns=["is_anomaly"]), "Download flagged records (CSV)", "flagged_anomalies.csv", "dl_anom")

st.subheader("Time-series view")
states = sorted(scored["state"].unique())
default_state = flagged["state"].iloc[0] if len(flagged) else states[0]
s = st.selectbox("State", states, index=states.index(default_state))
d = scored[scored["state"] == s]
ui.high_usage_warning(d[d["is_anomaly"] & (d["direction"] == "High")])
fig = go.Figure()
fig.add_scatter(x=d["period"], y=d["observed"], name="Observed", mode="lines", line=dict(color=ui.PALETTE[0]))
fig.add_scatter(x=d["period"], y=d["baseline"], name="Baseline (expected)", mode="lines", line=dict(color=ui.PALETTE[4], dash="dot"))
for direction, name, color, symbol in (
    ("High", "High usage warning", ui.PALETTE[3], "triangle-up"),
    ("Low", "Low anomaly", ui.PALETTE[2], "diamond"),
):
    f = d[d["is_anomaly"] & (d["direction"] == direction)]
    fig.add_scatter(x=f["period"], y=f["observed"], name=name, mode="markers",
                    marker=dict(color=color, size=11, symbol=symbol),
                    customdata=f[["deviation_pct", "score"]],
                    hovertemplate="%{x|%b %Y}<br>%{y:,.1f}<br>deviation %{customdata[0]:.1f}%<br>"
                                  "score %{customdata[1]:.2f}<extra></extra>")
fig.update_layout(title=f"{s}: {avail[metric]}", yaxis_title=avail[metric], hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
st.caption("Limitations: few years per group make estimates noisy; a data revision or a one-off event can look identical to a fault.")
ui.source_panel()
