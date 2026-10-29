"""Setup checker. Run from the project root:

    python scripts/check_setup.py              # checks packages, .env and the MySQL connection
    python scripts/check_setup.py --init-db    # additionally creates the database and tables

It reports problems; it never invents or inserts data.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ok = True


def step(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"[{'OK' if good else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))


step("Python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])
for mod in ["streamlit", "pandas", "numpy", "plotly", "sqlalchemy", "pymysql", "dotenv", "openpyxl", "cryptography"]:
    try:
        m = importlib.import_module(mod)
        step(f"package {mod}", True, getattr(m, "__version__", ""))
    except ImportError:
        step(f"package {mod}", False, "run: pip install -r requirements.txt")
if not ok:
    sys.exit("Fix the packages above, then re-run.")

from src import database as db  # noqa: E402

step(".env file present", (Path(__file__).resolve().parents[1] / ".env").exists(), "copy .env.example to .env and edit it")
if "--init-db" in sys.argv:
    good, msg = db.init_schema()
    step("create database + tables", good, msg)
good, msg = db.test_connection()
step("MySQL connection", good, msg)
if good:
    try:
        n = db.run_query("SELECT COUNT(*) AS n FROM power_supply_monthly")["n"][0]
        step("tables exist", True, f"power_supply_monthly has {n} rows")
        vr = db.run_query("SELECT VERSION() AS v")["v"][0]
        step("MySQL version >= 8.0 (window functions)", not vr.startswith(("5.", "4.")), vr)
        for q in [q for q in db.load_sql_library() if q["file"] == "data_quality.sql"]:
            try:
                db.run_query(q["sql"])
                step(f"query {q['name']}", True)
            except Exception as e:  # noqa: BLE001
                step(f"query {q['name']}", False, str(e).splitlines()[0][:200])
    except Exception as e:  # noqa: BLE001
        step("tables exist", False, "run again with --init-db  (" + str(e).splitlines()[0][:120] + ")")
print("\nAll checks passed." if ok else "\nSome checks failed - see above.")
sys.exit(0 if ok else 1)
