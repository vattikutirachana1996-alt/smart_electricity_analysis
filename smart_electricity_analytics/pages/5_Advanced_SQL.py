import pandas as pd
import plotly.express as px
import streamlit as st
from src import database as db, ui

ui.setup("Advanced SQL Insights", "🧮", "Every query below is read from the /sql folder and executed on your MySQL database")
ui.get_data()  # shows friendly errors / empty states and stops if no data
lib = db.load_sql_library()
files = sorted({q["file"] for q in lib})
f = st.sidebar.selectbox("SQL file", files)
qs = [q for q in lib if q["file"] == f]
q = st.selectbox("Query", qs, format_func=lambda q: f"{q['name'].split('_')[0].upper()} - {q['title']}")
st.markdown(f"**Technique:** {q['feature'] or 'SQL'} &nbsp;|&nbsp; **File:** `sql/{q['file']}`")
st.code(q["sql"], language="sql")

if st.button("Run query on MySQL", type="primary"):
    try:
        with st.spinner("Running query..."):
            res = db.run_query(q["sql"])
    except Exception as e:  # noqa: BLE001
        st.error(f"Query failed: {type(e).__name__}: {str(e).splitlines()[0][:400]}")
        st.caption("Window functions and CTEs need MySQL 8.0 or later.")
        st.stop()
    if res.empty:
        st.success("The query ran successfully and returned 0 rows (for data-quality checks this usually means no issues were found).")
    else:
        st.dataframe(res, hide_index=True, use_container_width=True)
        ui.download_button(res, "Download result (CSV)", f"{q['name']}.csv", "dl_sql")
        # automatic chart: first date column on x, first numeric column on y
        date_col = next((c for c in res.columns if c in ("period_month", "prev_month", "first_month")), None)
        if date_col:
            res[date_col] = pd.to_datetime(res[date_col], errors="coerce")
        num = [c for c in res.select_dtypes("number").columns if c not in ("states_reporting", "months_gap", "fy_start")]
        cat = next((c for c in ("state_name", "region_name", "bucket") if c in res.columns), None)
        if date_col and num:
            st.plotly_chart(px.line(res.head(5000), x=date_col, y=num[0], color=cat if cat and res[cat].nunique() <= 12 else None,
                                    color_discrete_sequence=ui.PALETTE, title=f"{num[0]} over time"), use_container_width=True)
        elif cat and num:
            st.plotly_chart(px.bar(res.head(60), x=num[0], y=cat, orientation="h", color_discrete_sequence=ui.PALETTE), use_container_width=True)
else:
    st.caption("Press the button to execute. Results are never hardcoded.")

with st.expander("Techniques demonstrated"):
    st.markdown("CTEs - `LAG()` - `RANK()` / `DENSE_RANK()` / `ROW_NUMBER()` - window frames (3-month moving average) - "
                "running totals - self-join year-on-year - multi-table joins - `HAVING` completeness filters - data-quality checks.")
