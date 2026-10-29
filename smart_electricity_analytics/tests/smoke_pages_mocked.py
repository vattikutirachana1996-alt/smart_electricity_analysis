"""MOCKED smoke test of every Streamlit page. Run:  python tests/smoke_pages_mocked.py

This is NOT a real Streamlit / MySQL test. It replaces streamlit, plotly, sqlalchemy and the database
layer with stand-ins so the pages' own Python code runs against SYNTHETIC data and exposes NameErrors,
bad attribute use, pandas errors and broken control flow. It cannot verify rendering, widget behaviour,
Plotly argument validity or any SQL. Use the real app + MySQL for that.
"""
import io, runpy, sys, types
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.synthetic_fixtures import make_series  # noqa: E402

MESSAGES = []


class StopApp(Exception):
    pass


class Fake:
    """Stand-in for the streamlit module and for column / tab / expander containers."""
    sidebar = None

    def __init__(self, uploads=None):
        self.sidebar = self
        self.uploads = uploads
        self.session_state = {}

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def __getattr__(self, name):                       # any other widget: do nothing
        def f(*a, **k):
            return Fake(self.uploads)
        return f

    # --- widgets that return values the pages depend on
    def columns(self, n, **k):
        return [Fake(self.uploads) for _ in range(n if isinstance(n, int) else len(n))]
    def tabs(self, labels): return [Fake(self.uploads) for _ in labels]
    def expander(self, *a, **k): return Fake(self.uploads)
    def spinner(self, *a, **k): return Fake(self.uploads)
    def form(self, *a, **k): return Fake(self.uploads)
    def selectbox(self, label, options, index=0, **k):
        o = list(options); return o[index] if o else None
    def radio(self, label, options, index=0, **k): return list(options)[index]
    def multiselect(self, label, options=None, default=None, **k): return list(default or [])
    def slider(self, label, lo=0, hi=1, value=None, *a, **k): return lo if value is None else value
    def select_slider(self, label, options=None, value=None, **k): return value if value is not None else list(options)[0]
    def date_input(self, label, value=None, **k): return value
    def text_input(self, label, value="", **k): return value
    def text_area(self, label, value="", **k): return value
    def checkbox(self, *a, **k): return False
    def button(self, *a, **k): return False
    def form_submit_button(self, *a, **k): return False
    def file_uploader(self, *a, **k): return self.uploads
    def stop(self): raise StopApp()
    def set_page_config(self, **k): pass
    def error(self, m, *a, **k): MESSAGES.append(("error", str(m)))
    def warning(self, m, *a, **k): MESSAGES.append(("warning", str(m)))
    def info(self, m, *a, **k): MESSAGES.append(("info", str(m)))
    def success(self, m, *a, **k): MESSAGES.append(("success", str(m)))

    def cache_data(self, *a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda fn: fn
    cache_data = type("CD", (), {"__call__": lambda s, *a, **k: (a[0] if a and callable(a[0]) else (lambda fn: fn)),
                                  "clear": lambda s: None})()


class FakeFig:
    def __getattr__(self, n): return lambda *a, **k: self


def install_fakes(uploads=None):
    st = Fake(uploads)
    sys.modules["streamlit"] = st
    px = types.ModuleType("plotly.express")
    px.__getattr__ = lambda name: (lambda *a, **k: FakeFig())
    go = types.ModuleType("plotly.graph_objects")
    go.Figure = lambda *a, **k: FakeFig()
    pl = types.ModuleType("plotly"); pl.express, pl.graph_objects = px, go
    sys.modules.update({"plotly": pl, "plotly.express": px, "plotly.graph_objects": go})
    sa = MagicMock(); sys.modules.update({"sqlalchemy": sa, "sqlalchemy.engine": sa.engine, "pymysql": MagicMock()})
    for m in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    return st


def synthetic_db_frame():
    parts = []
    for i, (s, r) in enumerate([("Alpha", "Northern"), ("Beta", "Western"), ("Gamma", "Southern")]):
        d = make_series(s, base=500 * (i + 1), years=8, seed=i, spike=(4, 3, 1.5) if i == 0 else None)
        d["region"], d["source_id"] = r, 1
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def patch_db(connected=True, empty=False):
    from src import database as db
    db.test_connection = lambda: (connected, "Connected." if connected else "OperationalError: refused")
    db.load_power_supply = lambda: (synthetic_db_frame().iloc[0:0] if empty else synthetic_db_frame())
    db.load_sources = lambda: pd.DataFrame({"dataset_name": ["SYNTHETIC TEST"], "source_url": ["n/a"], "period_start": [None],
                                            "period_end": [None], "download_date": [None], "energy_unit": ["MU"],
                                            "power_unit": ["MW"], "frequency": ["Monthly"], "limitations": ["test"]})
    db.existing_overlap = lambda df: 0
    db.run_query = lambda sql: pd.DataFrame({"state_name": ["A", "A", "B"], "period_month": ["2020-04-01", "2020-05-01", "2020-04-01"],
                                             "value_mu": [1.0, 2.0, 3.0]})
    db.init_schema = lambda: (True, "ok")
    return db


def run(script, **kw):
    MESSAGES.clear()
    install_fakes(kw.pop("uploads", None))
    patch_db(**kw)
    try:
        runpy.run_path(str(ROOT / script), run_name="__main__")
        return "completed", list(MESSAGES)
    except StopApp:
        return "stopped (st.stop)", list(MESSAGES)


def synthetic_upload():
    d = synthetic_db_frame().rename(columns={"state": "State", "period": "Month", "energy_requirement_mu": "Energy Requirement (MU)",
                                              "energy_availability_mu": "Energy Availability (MU)", "peak_demand_mw": "Peak Demand (MW)",
                                              "peak_met_mw": "Peak Met (MW)"}).drop(columns=["region", "source_id"])
    d["State"] = d["State"].map({"Alpha": "Maharashtra", "Beta": "Orissa", "Gamma": "Tamil Nadu"})  # alias Orissa tests renaming
    d.loc[len(d)] = ["All India", pd.Timestamp("2014-04-01"), 1, 1, 1, 1]
    b = io.BytesIO(d.to_csv(index=False).encode()); b.name = "SYNTHETIC_TEST.csv"
    return b


if __name__ == "__main__":
    failures = 0
    cases = [("app.py", {}), *[(f"pages/{p.name}", {}) for p in sorted((ROOT / "pages").glob("*.py"))]]
    cases += [("app.py (db down)", {"connected": False}), ("pages/1_Overview.py (db down)", {"connected": False}),
              ("pages/1_Overview.py (empty db)", {"empty": True}),
              ("pages/6_Data_Management.py (with synthetic CSV)", {"uploads": synthetic_upload()})]
    for name, kw in cases:
        script = name.split(" (")[0]
        try:
            status, msgs = run(script, **kw)
            print(f"[OK]   {name}: {status}" + (f"  -> {msgs[0][0]}: {msgs[0][1][:70]}" if status.startswith("stopped") and msgs else ""))
        except Exception as e:  # noqa: BLE001
            failures += 1
            import traceback
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
            traceback.print_exc(limit=4)
    # import-button path: confirms what would be sent to MySQL (import itself is replaced by a recorder)
    MESSAGES.clear(); st = install_fakes(synthetic_upload()); db = patch_db(); calls = []
    db.import_power_supply = lambda df, meta, mode: calls.append((df, meta, mode)) or {"source_id": 1, "new_rows": len(df), "duplicates_found": 0, "duplicates_action": mode}
    Fake.form_submit_button = lambda self, *a, **k: True
    Fake.checkbox = lambda self, *a, **k: True
    Fake.text_input = lambda self, label, value="", **k: "https://cea.nic.in/example" if "URL" in label else (value or "SYNTHETIC TEST")
    try:
        runpy.run_path(str(ROOT / "pages/6_Data_Management.py"), run_name="__main__")
        df, meta, mode = calls[0]
        good = (set(df["state"]) == {"Maharashtra", "Odisha", "Tamil Nadu"} and "row_in_file" not in df and mode == "skip"
                and len(df) == 288 and df["period"].nunique() == 96 and df[["state", "period"]].duplicated().sum() == 0 and (df["period"].dt.day == 1).all())
        print(f"[{'OK' if good else 'FAIL'}] import payload: {len(df)} rows, states={sorted(df['state'].unique())}, mode={mode} (All-India row excluded, Orissa->Odisha)")
        failures += 0 if good else 1
    except Exception as e:  # noqa: BLE001
        failures += 1; print(f"[FAIL] import path: {type(e).__name__}: {e}")
    print(f"\n{len(cases) - failures}/{len(cases)} page scripts ran without Python errors (mocked environment).")
    sys.exit(1 if failures else 0)
