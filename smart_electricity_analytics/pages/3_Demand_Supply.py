import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src import ui, analytics as an

ui.setup("Demand and Supply Analysis", "🔌", "Energy in MU (million units = GWh) and peak power in MW are analysed separately")
raw = ui.get_data()
df = an.supply_gap(ui.sidebar_filters(raw))
has_energy = "energy_gap_mu" in df and df["energy_gap_mu"].notna().any()
has_peak = "peak_gap_mw" in df and df["peak_gap_mw"].notna().any()
if not (has_energy or has_peak):
    st.info("Upload data containing requirement + availability, or peak demand + peak met, to use this page.")
    st.stop()

tab_e, tab_p, tab_g = st.tabs(["Energy: requirement vs availability (MU)", "Peak: demand vs met (MW)", "Demand growth"])

with tab_e:
    if not has_energy:
        st.info("Energy requirement and availability columns are not both available.")
    else:
        e = df.dropna(subset=["energy_gap_mu"])
        nat = e.groupby("period").agg(req=("energy_requirement_mu", "sum"), avail=("energy_availability_mu", "sum"),
                                       n=("state", "nunique")).reset_index()
        nat["gap_mu"] = nat["req"] - nat["avail"]
        nat["gap_pct"] = nat["gap_mu"] / nat["req"] * 100
        fig = go.Figure()
        fig.add_scatter(x=nat["period"], y=nat["req"], name="Requirement (MU)", line=dict(color=ui.PALETTE[1]))
        fig.add_scatter(x=nat["period"], y=nat["avail"], name="Availability (MU)", line=dict(color=ui.PALETTE[0]))
        fig.update_layout(title="National monthly energy requirement vs availability", yaxis_title="MU", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        st.plotly_chart(px.bar(nat, x="period", y="gap_pct", title="National shortfall (+) / surplus (-) as % of requirement",
                               color_discrete_sequence=[ui.PALETTE[3]]), use_container_width=True)
        st.caption("Shortfall = requirement - availability. Positive means unmet energy; negative means availability exceeded requirement.")
        c1, c2 = st.columns(2)
        by_state = e.groupby("state").agg(shortfall_mu=("energy_gap_mu", "sum"), req=("energy_requirement_mu", "sum")).reset_index()
        by_state["shortfall_pct"] = by_state["shortfall_mu"] / by_state["req"] * 100
        c1.subheader("Largest cumulative shortfalls (MU)")
        c1.dataframe(by_state.nlargest(10, "shortfall_mu")[["state", "shortfall_mu", "shortfall_pct"]].round(2), hide_index=True, use_container_width=True)
        c2.subheader("Largest state-month shortfalls")
        c2.dataframe(ui.round2(e.nlargest(10, "energy_gap_mu")[["state", "period", "energy_requirement_mu", "energy_availability_mu", "energy_gap_mu", "energy_gap_pct"]]),
                     hide_index=True, use_container_width=True)
        st.plotly_chart(px.bar(by_state.sort_values("shortfall_pct"), x="shortfall_pct", y="state", orientation="h",
                               title="Cumulative shortfall (+) / surplus (-) by state, % of requirement",
                               height=max(400, 20 * len(by_state)), color_discrete_sequence=[ui.PALETTE[2]]), use_container_width=True)
        ui.download_button(e[["state", "region", "period", "energy_requirement_mu", "energy_availability_mu", "energy_gap_mu", "energy_gap_pct"]],
                           "Download energy gap table (CSV)", "energy_gap.csv", "dl_egap")

with tab_p:
    if not has_peak:
        st.info("Peak demand and peak met columns are not both available.")
    else:
        p = df.dropna(subset=["peak_gap_mw"])
        st.caption("Peaks occur at different times in different states, so state peaks are never summed into a national figure.")
        s = st.selectbox("State", sorted(p["state"].unique()))
        ps = p[p["state"] == s]
        fig = go.Figure()
        fig.add_scatter(x=ps["period"], y=ps["peak_demand_mw"], name="Peak demand (MW)", line=dict(color=ui.PALETTE[1]))
        fig.add_scatter(x=ps["period"], y=ps["peak_met_mw"], name="Peak met (MW)", line=dict(color=ui.PALETTE[0]))
        fig.update_layout(title=f"{s}: peak demand vs peak met", yaxis_title="MW", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        top = ui.round2(p.nlargest(15, "peak_gap_mw")[["state", "period", "peak_demand_mw", "peak_met_mw", "peak_gap_mw", "peak_gap_pct"]])
        st.subheader("Largest peak shortfalls (state-month)")
        st.dataframe(top, hide_index=True, use_container_width=True)
        ui.download_button(p[["state", "period", "peak_demand_mw", "peak_met_mw", "peak_gap_mw", "peak_gap_pct"]],
                           "Download peak gap table (CSV)", "peak_gap.csv", "dl_pgap")

with tab_g:
    metric = st.selectbox("Series", [m for m in ("energy_requirement_mu", "peak_demand_mw") if m in df and df[m].notna().any()])
    if metric == "energy_requirement_mu":
        fy = an.fy_totals(df, metric)
        if fy.empty:
            st.info("Needs at least one complete fiscal year.")
        else:
            top = st.multiselect("States", sorted(fy["state"].unique()), default=list(fy.groupby("state")["total"].sum().nlargest(5).index))
            g = fy[fy["state"].isin(top)]
            st.plotly_chart(px.line(g, x="fy", y="yoy_pct", color="state", markers=True, color_discrete_sequence=ui.PALETTE,
                                    title="Fiscal-year energy requirement growth (%)"), use_container_width=True)
    else:
        a = df.copy()
        a["fy_start"] = a["period"].dt.year - (a["period"].dt.month < 4).astype(int)
        mx = a.groupby(["state", "fy_start"])["peak_demand_mw"].max().reset_index()
        pick = st.multiselect("States", sorted(mx["state"].unique()), default=sorted(mx["state"].unique())[:4])
        st.plotly_chart(px.line(mx[mx["state"].isin(pick)], x="fy_start", y="peak_demand_mw", color="state", markers=True,
                                title="Highest monthly peak demand per fiscal year (MW)", color_discrete_sequence=ui.PALETTE), use_container_width=True)
        st.caption("A fiscal year with fewer than 12 months may understate its true maximum.")
ui.source_panel()
