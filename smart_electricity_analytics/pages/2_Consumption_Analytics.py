import plotly.express as px
import streamlit as st
from src import ui, analytics as an, anomaly_detection as ad
from src.config import AVAILABILITY_NOTE, METRICS

ui.setup("Consumption Analytics", "📈", "Energy availability is used as the consumption proxy (see note below)")
raw = ui.get_data()
df = ui.sidebar_filters(raw)
period_count = df["period"].nunique()
if period_count < 12:
    covered = df["period"].min().strftime("%b %Y") if period_count == 1 else (
        f"{df['period'].min():%b %Y} to {df['period'].max():%b %Y}"
    )
    st.info(
        f"The current data covers {covered} only ({period_count} distinct month(s)). "
        "Annual charts need a complete 12-month fiscal year, and trends need multiple months. "
        "Import the synthetic demo data from Data Management to explore all charts."
    )
en = ui.available_metrics(df, ["energy_availability_mu", "energy_requirement_mu"])
if not en:
    st.info("No energy columns found in the imported data.")
    st.stop()
metric = st.selectbox("Metric", list(en), format_func=en.get)
if metric == "energy_availability_mu":
    st.caption(AVAILABILITY_NOTE)
d = df.dropna(subset=[metric])
_, flagged, anomaly_info = ad.detect_anomalies(d, metric, "zscore", threshold=1.5, min_group=5)
high_usage = flagged[flagged["direction"] == "High"]
ui.high_usage_warning(high_usage)
if anomaly_info["rows_used"] == 0:
    st.caption("High-usage anomaly warnings need at least five complete fiscal years for comparison.")

t1, t2, t3, t4, t5 = st.tabs(["Trends", "State & region comparison", "Growth (MoM / YoY)", "Moving average", "Rankings & statistics"])

with t1:
    freq = st.radio("Granularity", ["Monthly", "Annual (fiscal year)"], horizontal=True)
    scope = st.radio("Series", ["National total", "By state", "By region"], horizontal=True)
    if freq == "Monthly":
        if scope == "National total":
            g = d.groupby("period")[metric].sum().reset_index()
            markers = g.merge(high_usage[["period"]].drop_duplicates(), on="period", how="inner")
            fig = ui.line(
                g, "period", metric, title="Monthly total (sum of reporting states)", ylabel="MU",
                markers=g["period"].nunique() == 1,
            )
        else:
            by = "state" if scope == "By state" else "region"
            g = d.groupby(["period", by])[metric].sum().reset_index()
            warning_keys = high_usage[["period", by]].drop_duplicates()
            markers = g.merge(warning_keys, on=["period", by], how="inner")
            fig = ui.line(
                g, "period", metric, by, ylabel="MU", markers=g["period"].nunique() == 1,
            )
        if not markers.empty:
            fig.add_scatter(
                x=markers["period"], y=markers[metric], mode="markers",
                name="High-usage warning",
                marker=dict(color="#C8553D", size=12, symbol="triangle-up"),
                hovertemplate="%{x|%b %Y}<br>High-usage anomaly<extra></extra>",
            )
        st.plotly_chart(fig, use_container_width=True)
    else:
        fy = an.fy_totals(d, metric)
        if fy.empty:
            st.info("No complete fiscal year (12 months) in the filtered range. Showing the available monthly values instead.")
            by = {"National total": None, "By state": "state", "By region": "region"}[scope]
            g = d.groupby(["period"] + ([by] if by else []))[metric].sum().reset_index()
            st.plotly_chart(px.bar(
                g, x="period", y=metric, color=by, barmode="group",
                color_discrete_sequence=ui.PALETTE,
                title="Observed monthly totals (annual totals unavailable)",
                labels={metric: "MU", "period": "Month"},
            ), use_container_width=True)
        else:
            by = {"National total": None, "By state": "state", "By region": "region"}[scope]
            g = fy.groupby(["fy"] + ([by] if by else []))["total"].sum().reset_index()
            st.plotly_chart(px.bar(g, x="fy", y="total", color=by, barmode="group", color_discrete_sequence=ui.PALETTE,
                                   labels={"total": "MU", "fy": "Fiscal year"}), use_container_width=True)
            st.caption("Only complete fiscal years (Apr-Mar, 12 reported months) are shown.")

with t2:
    fy = an.fy_totals(d, metric)
    if fy.empty:
        st.info("A fiscal-year comparison needs 12 months. Showing the latest available month instead.")
        latest_period = d["period"].max()
        latest = d[d["period"] == latest_period].groupby(["state", "region"])[metric].sum().reset_index()
        st.plotly_chart(px.bar(
            latest.sort_values(metric), x=metric, y="state", color="region", orientation="h",
            color_discrete_sequence=ui.PALETTE,
            title=f"State comparison for {latest_period:%b %Y}",
            labels={metric: "MU"},
            height=max(400, 22 * len(latest)),
        ), use_container_width=True)
        reg = latest.groupby("region")[metric].sum().reset_index()
        st.plotly_chart(px.pie(
            reg, names="region", values=metric, hole=.45,
            color_discrete_sequence=ui.PALETTE,
            title=f"Share by region, {latest_period:%b %Y}",
        ), use_container_width=True)
    else:
        years = sorted(fy["fy"].unique(), reverse=True)
        sel = st.selectbox("Fiscal year", years)
        y = fy[fy["fy"] == sel]
        n = st.slider("Top / bottom N", 3, 15, 5)
        a, b = st.columns(2)
        a.subheader(f"Highest {n}")
        a.dataframe(y.nlargest(n, "total")[["state", "region", "total"]], hide_index=True, use_container_width=True)
        b.subheader(f"Lowest {n}")
        b.dataframe(y.nsmallest(n, "total")[["state", "region", "total"]], hide_index=True, use_container_width=True)
        st.plotly_chart(px.bar(y.sort_values("total"), x="total", y="state", color="region", orientation="h",
                               color_discrete_sequence=ui.PALETTE, labels={"total": "MU"}, height=max(400, 22 * len(y))),
                        use_container_width=True)
        reg = y.groupby("region")["total"].sum().reset_index()
        st.plotly_chart(px.pie(reg, names="region", values="total", hole=.45, color_discrete_sequence=ui.PALETTE,
                               title="Share by region"), use_container_width=True)

with t3:
    ch = an.with_changes(d, metric)
    states = sorted(ch["state"].unique())
    pick = st.multiselect("States", states, default=states[:3], key="chg_states")
    c = ch[ch["state"].isin(pick)] if pick else ch
    x1, x2 = st.columns(2)
    if c["mom_pct"].notna().any():
        x1.plotly_chart(ui.line(
            c, "period", "mom_pct", "state", "Month-on-month change (%)", "%",
            markers=c["period"].nunique() <= 2,
        ), use_container_width=True)
    else:
        x1.info("Month-on-month change needs consecutive months in the selected data.")
    if c["yoy_pct"].notna().any():
        x2.plotly_chart(ui.line(
            c, "period", "yoy_pct", "state", "Year-on-year change (%) - same month last year", "%",
            markers=c["period"].nunique() <= 2,
        ), use_container_width=True)
    else:
        x2.info("Year-on-year change needs data for the same month in the previous year.")
    st.caption("Percentage changes are computed only against the exact previous month / same month last year; gaps give blanks.")
    ui.download_button(ch, "Download growth table (CSV)", "growth_table.csv", "dl_growth")

with t4:
    window_options = [window for window in (3, 6, 12) if window <= d["period"].nunique()]
    if not window_options:
        window_options = [d["period"].nunique()]
    w = st.select_slider("Window (months)", window_options, value=window_options[0])
    ma = an.moving_average(d, metric, w)
    pick = st.multiselect("States", sorted(ma["state"].unique()), default=sorted(ma["state"].unique())[:2], key="ma_states")
    m = ma[ma["state"].isin(pick)] if pick else ma
    ma_column = f"ma{w}"
    if not m[ma_column].notna().any():
        st.info("No complete consecutive-month window is available. Showing the observed monthly values instead.")
        st.plotly_chart(ui.line(
            m, "period", metric, "state", "Observed monthly values", "MU",
            markers=m["period"].nunique() <= 2,
        ), use_container_width=True)
    else:
        long = m.melt(["state", "period"], [metric, ma_column], var_name="series", value_name="MU")
        long["series"] = long["series"].map({metric: "Actual", ma_column: f"{w}-month average"})
        if len(pick) == 1:
            st.plotly_chart(ui.line(
                long, "period", "MU", "series", ylabel="MU",
                markers=m["period"].nunique() <= w,
            ), use_container_width=True)
        else:
            st.plotly_chart(ui.line(
                m, "period", ma_column, "state", f"{w}-month moving average", "MU",
                markers=m.groupby("state")[ma_column].count().max() <= 1,
            ), use_container_width=True)
        st.caption("A moving average is blank until a full window of consecutive months is available.")

with t5:
    fy = an.rank_states(an.fy_totals(d, metric))
    if not fy.empty:
        latest = fy[fy["fy_start"] == fy["fy_start"].max()].sort_values("rank_total")
        st.subheader(f"Ranking and growth, FY {latest['fy'].iloc[0]}")
        st.dataframe(latest[["rank_total", "state", "region", "total", "yoy_pct", "rank_growth"]]
                     .rename(columns={"total": "total_MU", "yoy_pct": "yoy_growth_%"}), hide_index=True, use_container_width=True)
        nat = fy.groupby("fy_start")["total"].sum()
        est = an.linear_trend_estimate(nat)
        if est["ok"]:
            st.caption(f"Illustrative linear trend of summed state totals: {est['slope_per_year']:,.0f} MU per year, "
                       f"R^2 = {est['r2']:.2f} over {est['n_years']} years. This is a descriptive estimate, not a forecast; "
                       "it ignores state coverage changes, shocks and non-linear growth.")
    st.subheader("Descriptive statistics by state")
    st.dataframe(an.describe(d, metric), hide_index=True, use_container_width=True)
    prof = an.seasonal_profile(d, metric)
    if not prof.empty:
        st.plotly_chart(px.bar(prof, x="month", y="share_pct", title="Average share of fiscal-year total by calendar month (%)",
                               color_discrete_sequence=[ui.PALETTE[0]]), use_container_width=True)
ui.source_panel()
