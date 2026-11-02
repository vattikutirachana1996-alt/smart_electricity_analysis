import datetime as dt
import pandas as pd
import streamlit as st
from src import database as db, ui, preprocessing as pp, validation as val
from src.config import ENERGY_TO_MU, POWER_TO_MW, METRICS, ROOT

ui.setup("Data Management", "🗂️", "Upload official CEA or clearly labeled demo data, validate it, then import into MySQL")

ok, msg = db.test_connection()
st.sidebar.write("MySQL:", "🟢 connected" if ok else "🔴 not connected")
if not ok:
    st.error(msg)
    st.caption("Set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME in `.env`. If the database does not exist yet, the button below can create it.")
if st.button("Create / verify schema (runs sql/schema.sql)"):
    good, m = db.init_schema()
    (st.success if good else st.error)(m)
    st.cache_data.clear()

demo_path = ROOT / "data" / "demo" / "SYNTHETIC_demo_monthly_power_supply.csv"
st.subheader("Try the dashboard with demo data")
st.download_button(
    "Download synthetic demo CSV",
    demo_path.read_bytes(),
    file_name=demo_path.name,
    mime="text/csv",
)
demo_ack = st.checkbox("I understand the demo values are simulated, not official data")
if st.button("Import demo data into MySQL", type="primary"):
    if not ok:
        st.error("MySQL is not connected. Connect to the database before importing demo data.")
    elif not demo_ack:
        st.error("Please acknowledge that this is simulated demo data before importing.")
    else:
        demo_raw = pd.read_csv(demo_path)
        demo_mapping = pp.guess_mapping(demo_raw.columns)
        demo_result = pp.build_clean(demo_raw, demo_mapping)
        for issue in demo_result.issues:
            {"error": st.error, "warning": st.warning, "info": st.info}[issue["level"]](issue["message"])
        if demo_result.has_errors or demo_result.data.empty:
            st.error("The built-in demo dataset could not be prepared for import.")
        else:
            demo_clean = demo_result.data.drop(columns=["row_in_file"])
            existing = db.existing_overlap(demo_clean)
            if existing == len(demo_clean):
                st.info("All demo rows are already in the database; no rows were added.")
            else:
                try:
                    with st.spinner("Importing synthetic demo data..."):
                        result = db.import_power_supply(
                            demo_clean,
                            {
                                "dataset_name": "Synthetic demo monthly power supply data",
                                "source_url": "Not applicable - synthetic demo data",
                                "publisher": "Synthetic demo data (not official)",
                                "download_date": dt.date.today(),
                                "frequency": "Monthly",
                                "coverage": "10 sample states",
                                "limitations": (
                                    "Synthetic simulated values for software demonstrations only. Not official "
                                    "CEA data and not suitable for research, reporting, or real-world conclusions."
                                ),
                                "file_name": demo_path.name,
                            },
                            "skip",
                        )
                    st.cache_data.clear()
                    st.success(
                        f"Demo import complete: {result['new_rows']} new monthly rows added; "
                        f"{result['duplicates_found']} existing rows skipped. Open Consumption Analytics "
                        "and select April 2019–March 2024."
                    )
                except Exception as e:  # noqa: BLE001
                    st.error(
                        f"Demo import failed and was rolled back; nothing was written. "
                        f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
                    )

st.header("1. Upload file")
st.info("For a ready-to-use example, upload `data/demo/SYNTHETIC_demo_monthly_power_supply.csv`. "
        "It contains simulated values for 10 states over 5 years so the charts can be explored. "
        "It is not official CEA data and must not be used for research or reporting.")
st.markdown("Download the official CEA table (see `docs/DATA_SOURCES.md`). CEA monthly reports are published as PDF; "
            "extract the state table to CSV/Excel first. Required: a **state** column and a **month/date** column, "
            "plus at least one metric.")
up = st.file_uploader("CSV or Excel", type=["csv", "xlsx"])
if not up:
    st.info("Upload a file to begin.")
    st.stop()
try:
    if up.name.lower().endswith(".csv"):
        try:
            raw = pd.read_csv(up)
        except UnicodeDecodeError:       # files saved from Excel are often Windows-1252
            up.seek(0)
            raw = pd.read_csv(up, encoding="latin-1")
    else:
        sheets = pd.ExcelFile(up).sheet_names
        sheet = st.selectbox("Sheet", sheets)
        up.seek(0)
        raw = pd.read_excel(up, sheet_name=sheet)
except Exception as e:  # noqa: BLE001
    st.error(f"Could not read the file: {e}")
    st.stop()
raw = raw.dropna(how="all")
raw.columns = [str(c).strip() for c in raw.columns]
is_demo = (
    "data_type" in raw.columns
    and not raw.empty
    and raw["data_type"].astype("string").str.strip().str.casefold().eq("synthetic - not official").all()
)
st.caption(f"{len(raw):,} rows, {len(raw.columns)} columns")
st.dataframe(raw.head(10), use_container_width=True)

st.header("2. Map columns and units")
guess = pp.guess_mapping(list(raw.columns))
opts = ["(not in file)"] + list(raw.columns)
labels = {"state": "State / UT", "period": "Month / date", **METRICS}
mapping = {}
cols = st.columns(3)
for i, (k, lab) in enumerate(labels.items()):
    g = guess.get(k)
    mapping[k] = None if (v := cols[i % 3].selectbox(lab, opts, index=opts.index(g) if g in opts else 0, key=f"map_{k}")) == "(not in file)" else v
u1, u2 = st.columns(2)
e_unit = u1.selectbox("Energy unit in the file", list(ENERGY_TO_MU), help="Values are converted to MU (1 MU = 1 GWh).")
p_unit = u2.selectbox("Power unit in the file", list(POWER_TO_MW), help="Values are converted to MW.")

st.header("3. Validate and preview")
res = pp.build_clean(raw, mapping, e_unit, p_unit)
for i in res.issues:
    {"error": st.error, "warning": st.warning, "info": st.info}[i["level"]](i["message"])
if res.has_errors or res.data.empty:
    st.stop()
clean = res.data
metric_cols = [c for c in clean.columns if c.endswith(("_mu", "_mw"))]
for i in val.range_issues(clean):
    {"error": st.error, "warning": st.warning}[i["level"]](i["message"])

t1, t2, t3, t4, t5 = st.tabs(["Preview", "Missing values", "Duplicates", "State names", "Excluded rows"])
t1.dataframe(clean.head(50), use_container_width=True, hide_index=True)
t1.caption(f"{len(clean):,} rows ready | {clean['state'].nunique()} states | {clean['period'].min():%b %Y} to {clean['period'].max():%b %Y}")
t2.dataframe(val.missing_report(clean, metric_cols), hide_index=True, use_container_width=True)
gaps = val.month_gaps(clean)
t2.write("Month gaps inside each state's range:")
t2.dataframe(gaps, hide_index=True, use_container_width=True) if len(gaps) else t2.success("No month gaps.")
dups = val.duplicate_rows(clean)
if len(dups):
    t3.error(f"{len(dups)} rows share a state + month with another row in this file.")
    t3.dataframe(dups, hide_index=True, use_container_width=True)
else:
    t3.success("No duplicate state + month rows in the file.")
t4.dataframe(res.state_map, hide_index=True, use_container_width=True)
t5.dataframe(res.excluded, hide_index=True, use_container_width=True) if len(res.excluded) else t5.success("No rows excluded.")
if len(res.excluded):
    ui.download_button(res.excluded, "Download excluded rows (CSV)", "excluded_rows.csv", "dl_excl")

st.header("4. Source documentation and import")
with st.form("meta"):
    a, b = st.columns(2)
    name = a.text_input(
        "Dataset / report name *",
        value="Synthetic demo monthly power supply data" if is_demo else "",
        placeholder="e.g. CEA Monthly Power Supply Position Report, FY 2023-24",
    )
    if is_demo:
        b.info("Source: simulated example data generated for app testing; no official source URL.")
        url = ""
    else:
        url = b.text_input("Official source URL *", placeholder="https://cea.nic.in/...")
    dl = a.date_input("Download date", dt.date.today())
    freq = b.text_input("Frequency", "Monthly")
    cov = a.text_input(
        "Geographic coverage",
        "10 sample states" if is_demo else "States / UTs of India",
    )
    default_limitations = (
        "Synthetic simulated values for software demonstrations only. Not official CEA data and not suitable for "
        "research, reporting, or real-world conclusions."
        if is_demo else
        "Energy availability includes transmission losses; it is not metered end-use consumption."
    )
    lim = a.text_area("Limitations / notes", default_limitations)
    dup_policy = st.radio("If a state + month already exists in MySQL",
                          ["Skip existing rows (keep database values)", "Overwrite existing rows with this file"])
    keep_last = bool(len(dups)) and st.checkbox("Keep the LAST occurrence of duplicate rows inside this file (others will be dropped)")
    confirm = st.checkbox(
        "I understand this is simulated demo data, not official CEA data"
        if is_demo else "I confirm this data comes from an official CEA publication"
    )
    go = st.form_submit_button("Import into MySQL", type="primary")

overlap = db.existing_overlap(clean) if ok else 0
if overlap:
    st.warning(f"{overlap} state-month rows in this file already exist in the database.")
if go:
    if not name.strip():
        st.error("A dataset / report name is required.")
    elif not is_demo and not url.strip().startswith("http"):
        st.error("Dataset name and a valid official source URL are required.")
    elif not confirm:
        st.error("Please confirm the data source.")
    elif len(dups) and not keep_last:
        st.error("Resolve duplicates first: tick the 'keep last occurrence' option or fix the file.")
    elif not ok:
        st.error("Database is not connected.")
    else:
        final = clean.drop_duplicates(["state", "period"], keep="last") if keep_last else clean
        try:
            with st.spinner("Importing..."):
                r = db.import_power_supply(final.drop(columns=["row_in_file"]),
                    {"dataset_name": name.strip(),
                     "source_url": url.strip() if not is_demo else "Not applicable - synthetic demo data",
                     "publisher": "Synthetic demo data (not official)" if is_demo
                     else "Central Electricity Authority (CEA), Ministry of Power, Govt. of India",
                     "download_date": dl, "frequency": freq, "coverage": cov, "limitations": lim,
                     "file_name": up.name},
                    "overwrite" if dup_policy.startswith("Overwrite") else "skip")
            st.cache_data.clear()
            st.success(f"Import complete (source id {r['source_id']}): {r['new_rows']} new rows, {r['duplicates_found']} already existed "
                       f"({'overwritten' if r['duplicates_action']=='overwrite' else 'skipped'}). {len(clean)-len(final)} in-file duplicates dropped by your choice.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Import failed and was rolled back; nothing was written. {type(e).__name__}: {str(e).splitlines()[0][:300]}")

st.header("Registered data sources")
if ok:
    try:
        st.dataframe(db.load_sources(), hide_index=True, use_container_width=True)
    except Exception:  # noqa: BLE001
        st.caption("Schema not created yet.")
