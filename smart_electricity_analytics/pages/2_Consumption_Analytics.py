import plotly.express as px
import streamlit as st
from src import ui, analytics as an
from src.config import AVAILABILITY_NOTE, METRICS

ui.setup("Consumption Analytics", "📈", "Energy availability is used as the consumption proxy (see note below)")
raw = ui.get_data()
df = ui.sidebar_filters(raw)
en = ui.available_metrics(df, ["energy_availability_mu", "energy_requirement_mu"])
if not en:
    st.info("No energy columns found in the imported data.")
    st.stop()
metric = st.selectbox("Metric", list(en), format_func=en.get)
if metric == "energy_availability_mu":
    st.caption(AVAILABILITY_NOTE)
d = df.dropna(subset=[metric])

t1, t2, t3, t4, t5 = st.tabs(["Trends", "State & region comparison", "Growth (MoM / YoY)", "Moving average", "Rankings & statistics"])

with t1:
    freq = st.radio("Granularity", ["Monthly", "Annual (fiscal year)"], horizontal=True)
    scope = st.radio("Series", ["National total", "By state", "By region"], horizontal=True)
    if freq == "Monthly":
        if scope == "National total":
            g = d.groupby("period")[metric].sum().reset_index()
            st.plotly_chart(ui.line(g, "period", metric, title="Monthly total (sum of reporting states)", ylabel="MU"), use_container_width=True)
        else:
            by = "state" if scope == "By state" else "region"
            g = d.groupby(["period", by])[metric].sum().reset_index()
            st.plotly_chart(ui.line(g, "period", metric, by, ylabel="MU"), use_container_width=True)
    else:
        fy = an.fy_totals(d, metric)
        if fy.empty:
            st.info("No complete fiscal year (12 months) in the filtered range.")
        else:
            by = {"National total": None, "By state": "state", "By region": "region"}[scope]
            g = fy.groupby(["fy"] + ([by] if by else []))["total"].sum().reset_index()
            st.plotly_chart(px.bar(g, x="fy", y="total", color=by, barmode="group", color_discrete_sequence=ui.PALETTE,
                                   labels={"total": "MU", "fy": "Fiscal year"}), use_container_width=True)
            st.caption("Only complete fiscal years (Apr-Mar, 12 reported months) are shown.")

with t2:
    fy = an.fy_totals(d, metric)
    if fy.empty:
        st.info("Comparison needs one complete fiscal year in the filtered range.")
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
    x1.plotly_chart(ui.line(c, "period", "mom_pct", "state", "Month-on-month change (%)", "%"), use_container_width=True)
    x2.plotly_chart(ui.line(c, "period", "yoy_pct", "state", "Year-on-year change (%) - same month last year", "%"), use_container_width=True)
    st.caption("Percentage changes are computed only against the exact previous month / same month last year; gaps give blanks.")
    ui.download_button(ch, "Download growth table (CSV)", "growth_table.csv", "dl_growth")

with t4:
    w = st.select_slider("Window (months)", [3, 6, 12], value=3)
    ma = an.moving_average(d, metric, w)
    pick = st.multiselect("States", sorted(ma["state"].unique()), default=sorted(ma["state"].unique())[:2], key="ma_states")
    m = ma[ma["state"].isin(pick)] if pick else ma
    long = m.melt(["state", "period"], [metric, f"ma{w}"], var_name="series", value_name="MU")
    long["series"] = long["series"].map({metric: "Actual", f"ma{w}": f"{w}-month average"})
    if len(pick) == 1:
        st.plotly_chart(ui.line(long, "period", "MU", "series", ylabel="MU"), use_container_width=True)
    else:
        st.plotly_chart(ui.line(m, "period", f"ma{w}", "state", f"{w}-month moving average", "MU"), use_container_width=True)
    st.caption("A moving average is blank where fewer than the full window of consecutive months exists.")

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
