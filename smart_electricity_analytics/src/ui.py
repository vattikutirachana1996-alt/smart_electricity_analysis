"""Shared Streamlit helpers: theme, data loading with friendly empty states, sidebar filters."""
import pandas as pd
import streamlit as st
import plotly.express as px
from . import database as db
from .config import METRICS

PALETTE = ["#0B6E4F", "#F2A900", "#1D4E89", "#C8553D", "#6C757D", "#2A9D8F", "#8E5572", "#264653"]
CSS = """
<style>
.block-container {padding-top: 1.4rem;}
[data-testid="stMetric"] {background:#F4F8F6; border:1px solid #D5E5DD; border-left:5px solid #0B6E4F;
  padding:10px 14px; border-radius:8px;}
@media (prefers-color-scheme: dark) {[data-testid="stMetric"] {background:#16231E; border-color:#2C4A3E;}}
.small-note {font-size:0.85rem; opacity:0.8;}
</style>"""


def setup(title: str, icon: str = "⚡", subtitle: str = ""):
    st.set_page_config(page_title=f"{title} | Smart Electricity Analytics", page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)
    st.sidebar.caption("Source: user-imported dataset. See the data source and reporting period below.")


@st.cache_data(ttl=30, show_spinner=False)
def _load() -> pd.DataFrame:
    return db.load_power_supply()


@st.cache_data(ttl=30, show_spinner=False)
def _sources() -> pd.DataFrame:
    return db.load_sources()


def get_data() -> pd.DataFrame:
    ok, msg = db.test_connection()
    if not ok:
        st.error(f"Cannot connect to MySQL. {msg}")
        st.info("Check your `.env` file (see `.env.example`), make sure MySQL is running, then open "
                "**Data Management** to create the schema.")
        st.stop()
    try:
        with st.spinner("Loading data from MySQL..."):
            df = _load()
    except Exception as e:  # noqa: BLE001
        st.warning("The database is reachable but the tables are not ready. Open **Data Management** and click "
                   f"'Create / verify schema'. ({type(e).__name__})")
        st.stop()
    if df.empty:
        st.info("No data has been imported yet. Go to **Data Management** to import a dataset or the synthetic demo.")
        st.stop()
    return df


def source_panel():
    try:
        src = _sources()
    except Exception as e:  # noqa: BLE001
        st.warning(f"Could not load registered data sources ({type(e).__name__}).")
        return
    with st.expander("Data source and reporting period", expanded=True):
        if src.empty:
            st.info("No data sources have been registered yet. Import a dataset from Data Management.")
            return
        columns = ["dataset_name", "publisher", "source_url", "period_start", "period_end", "download_date",
                   "energy_unit", "power_unit", "frequency", "limitations"]
        s = src[[column for column in columns if column in src]]
        st.dataframe(s, hide_index=True, use_container_width=True)


def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")
    regions = sorted(df["region"].dropna().unique())
    sel_r = st.sidebar.multiselect("Region", regions)
    d = df[df["region"].isin(sel_r)] if sel_r else df
    sel_s = st.sidebar.multiselect("State / UT", sorted(d["state"].unique()))
    if sel_s:
        d = d[d["state"].isin(sel_s)]
    lo, hi = d["period"].min().date(), d["period"].max().date()
    date_key = f"date_range_{lo.isoformat()}_{hi.isoformat()}"
    if st.sidebar.button("Reset date range to all available data"):
        if date_key in st.session_state:
            del st.session_state[date_key]
    rng = st.sidebar.date_input(
        "Date range",
        (lo, hi),
        key=date_key,
        help="Data is monthly: selecting any day includes that whole month. Only months present in the imported data are shown.",
    )
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        months = d["period"].dt.to_period("M")
        start_month, end_month = pd.Period(rng[0], freq="M"), pd.Period(rng[1], freq="M")
        d = d[(months >= start_month) & (months <= end_month)]
    if d.empty:
        available = lo.strftime("%b %Y") if lo == hi else f"{lo:%b %Y} to {hi:%b %Y}"
        st.info(
            f"No records are available for the selected months. The current data selection covers "
            f"{available}. Choose a range that includes those months, or import data for the selected period."
        )
        st.stop()
    return d


def available_metrics(df: pd.DataFrame, subset=None) -> dict:
    keys = subset or list(METRICS)
    return {k: METRICS[k] for k in keys if k in df and df[k].notna().any()}


def high_usage_warning(flagged: pd.DataFrame):
    """Show the latest detected high-usage anomaly from a flagged-records DataFrame."""
    high = flagged[flagged["direction"] == "High"]
    if high.empty:
        return
    latest = high.sort_values(["period", "state"]).iloc[-1]
    st.warning(
        f"High-usage anomaly detected in {len(high)} state-month record(s). Most recent: "
        f"{latest['state']} in {latest['period']:%b %Y}, "
        f"{latest['deviation_pct']:.1f}% above its expected baseline. "
        "Review the highlighted graph point; this statistical signal is not a diagnosis."
    )


def fmt(v: float, unit: str = "") -> str:
    if v is None or pd.isna(v):
        return "n/a"
    a = abs(v)
    s = f"{v/1e6:,.2f} M" if a >= 1e6 else f"{v/1e3:,.1f} k" if a >= 1e5 else f"{v:,.1f}"
    return f"{s} {unit}".strip()


def line(df, x, y, color=None, title="", ylabel="", markers=False):
    fig = px.line(df, x=x, y=y, color=color, title=title, color_discrete_sequence=PALETTE, markers=markers)
    fig.update_layout(yaxis_title=ylabel, legend_title_text="", margin=dict(t=50, l=10, r=10, b=10), hovermode="x unified")
    return fig


def download_button(df: pd.DataFrame, label: str, filename: str, key: str):
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), filename, "text/csv", key=key)


def round2(df: pd.DataFrame) -> pd.DataFrame:
    """Round numeric columns only (DataFrame.round warns on datetime columns in pandas 3)."""
    return df.round({c: 2 for c in df.select_dtypes("number").columns})
