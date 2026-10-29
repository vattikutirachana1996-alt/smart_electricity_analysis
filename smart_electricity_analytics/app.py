"""Home page. Run with:  streamlit run app.py"""
import streamlit as st
from src import database as db
from src.config import AVAILABILITY_NOTE
from src import ui

ui.setup("Smart Electricity Consumption Analytics", "⚡",
         "Indian electricity supply analysis using official CEA data, MySQL window-function SQL and statistical anomaly detection")

ok, msg = db.test_connection()
c1, c2 = st.columns([1, 2])
with c1:
    st.metric("Database", "Connected" if ok else "Not connected")
with c2:
    if ok:
        try:
            df = ui._load()
            st.metric("Rows loaded", f"{len(df):,}" if not df.empty else "0 (import data first)")
        except Exception:  # noqa: BLE001
            st.warning("Connected, but tables are missing. Open Data Management -> Create / verify schema.")
    else:
        st.error(msg)

st.subheader("What this application does")
st.markdown("""
1. **Overview** - KPIs, national trend, state comparison, year-on-year growth
2. **Consumption Analytics** - monthly/annual trends, rankings, MoM/YoY change, moving averages
3. **Demand & Supply** - requirement vs availability (MU) and peak demand vs peak met (MW)
4. **Anomaly Detection** - Z-score / IQR on scale- and trend-adjusted values, with CSV export
5. **Advanced SQL** - CTEs, LAG, RANK/DENSE_RANK, moving averages, running totals executed on MySQL
6. **Data Management** - upload CEA files, map columns, validate, preview, import
""")
st.subheader("Important data note")
st.info(AVAILABILITY_NOTE + " CEA does not publish a state-wise metered consumption series in the same "
        "monthly reports, so this project analyses **electricity supply position** and labels it clearly.")
st.caption("The application contains no built-in data. Everything shown comes from official CEA files that you upload.")
ui.source_panel() if ok else None
