"""MySQL access via SQLAlchemy + PyMySQL. Credentials come from environment variables / .env."""
from __future__ import annotations
import os
import re
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from .config import SQL_DIR

load_dotenv()
_engine: Engine | None = None


def _setting(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    try:
        value = st.secrets.get(name)
    except Exception:  # noqa: BLE001 - secrets may be absent during local development
        value = None
    return str(value) if value is not None else default


def _url(with_db: bool = True) -> URL:
    return URL.create("mysql+pymysql", username=_setting("DB_USER", ""), password=_setting("DB_PASSWORD", ""),
                      host=_setting("DB_HOST", "localhost"), port=int(_setting("DB_PORT", "3306")),
                      database=_setting("DB_NAME", "electricity_analytics") if with_db else None)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})
    return _engine


def test_connection() -> tuple[bool, str]:
    """Never raises: returns (ok, human-readable message)."""
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True, "Connected to MySQL."
    except Exception as e:  # noqa: BLE001 - surfaced to the user as a message
        global _engine
        _engine = None
        return False, f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"


def init_schema() -> tuple[bool, str]:
    """Run sql/schema.sql (CREATE DATABASE + tables). Safe to repeat (IF NOT EXISTS)."""
    try:
        raw = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
        raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--"))
        stmts = [s.strip() for s in raw.split(";") if s.strip()]
        eng = create_engine(_url(with_db=False), connect_args={"connect_timeout": 5})
        with eng.begin() as c:
            for s in stmts:
                c.exec_driver_sql(s)
        eng.dispose()
        global _engine
        _engine = None
        return True, f"Schema ready ({len(stmts)} statements executed)."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"


def run_query(sql: str) -> pd.DataFrame:
    """Execute a raw SQL string (no bind parsing, so ':' and '%' are safe) and return a DataFrame."""
    with get_engine().connect() as c:
        return pd.read_sql_query(sql, c)


def load_power_supply() -> pd.DataFrame:
    sql = """SELECT st.state_name AS state, r.region_name AS region, p.period_month AS period,
                    p.energy_requirement_mu, p.energy_availability_mu, p.peak_demand_mw, p.peak_met_mw, p.source_id
             FROM power_supply_monthly p
             JOIN states st ON st.state_id = p.state_id
             LEFT JOIN regions r ON r.region_id = st.region_id
             ORDER BY st.state_name, p.period_month"""
    df = run_query(sql)
    df["period"] = pd.to_datetime(df["period"])
    for c in ("energy_requirement_mu", "energy_availability_mu", "peak_demand_mw", "peak_met_mw"):
        df[c] = pd.to_numeric(df[c])
    return df


def load_sources() -> pd.DataFrame:
    return run_query("SELECT * FROM data_sources ORDER BY imported_at DESC")


def _none(v):
    """NaN -> NULL and numpy scalars -> plain Python floats (PyMySQL cannot escape numpy types)."""
    return None if pd.isna(v) else float(v)


def import_power_supply(df: pd.DataFrame, meta: dict, on_duplicate: str = "skip") -> dict:
    """Import cleaned rows in one transaction (all-or-nothing).
    on_duplicate: 'skip' keeps existing DB rows; 'overwrite' updates only the metrics present in the upload."""
    if on_duplicate not in ("skip", "overwrite"):
        raise ValueError("on_duplicate must be 'skip' or 'overwrite'")
    if df.duplicated(["state", "period"]).any():
        raise ValueError("Upload still contains duplicate (state, month) rows; resolve them first.")
    metrics = [c for c in ("energy_requirement_mu", "energy_availability_mu", "peak_demand_mw", "peak_met_mw") if c in df]
    eng = get_engine()
    with eng.begin() as c:
        c.execute(text("""INSERT INTO data_sources (dataset_name, source_url, period_start, period_end, download_date,
                          energy_unit, power_unit, frequency, coverage, limitations, file_name, publisher)
                          VALUES (:dataset_name, :source_url, :period_start, :period_end, :download_date,
                          'MU', 'MW', :frequency, :coverage, :limitations, :file_name, :publisher)"""),
                  {**meta, "period_start": df["period"].min().date(), "period_end": df["period"].max().date(),
                   "publisher": meta.get("publisher", "Central Electricity Authority (CEA), Ministry of Power, Govt. of India")})
        source_id = c.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        for region in df["region"].dropna().unique():
            c.execute(text("INSERT IGNORE INTO regions (region_name) VALUES (:r)"), {"r": region})
        rmap = dict(c.execute(text("SELECT region_name, region_id FROM regions")).all())
        for st, rg in df[["state", "region"]].drop_duplicates().itertuples(index=False):
            c.execute(text("INSERT INTO states (state_name, region_id) VALUES (:s, :r) "
                           "ON DUPLICATE KEY UPDATE region_id = COALESCE(region_id, VALUES(region_id))"),
                      {"s": st, "r": rmap.get(rg)})
        smap = dict(c.execute(text("SELECT state_name, state_id FROM states")).all())
        existing = {(sid, pd.Timestamp(p)) for sid, p in
                    c.execute(text("SELECT state_id, period_month FROM power_supply_monthly")).all()}
        rows, n_new, n_dup = [], 0, 0
        for r in df.itertuples(index=False):
            sid = smap[r.state]
            dup = (sid, pd.Timestamp(r.period)) in existing
            n_dup += dup
            n_new += not dup
            if dup and on_duplicate == "skip":
                continue
            rows.append({"sid": sid, "p": r.period.date(), "src": source_id,
                         **{m: _none(getattr(r, m)) for m in metrics}})
        if rows:
            cols = ", ".join(metrics)
            vals = ", ".join(f":{m}" for m in metrics)
            upd = ", ".join(f"{m} = COALESCE(VALUES({m}), {m})" for m in metrics)
            c.execute(text(f"INSERT INTO power_supply_monthly (state_id, period_month, {cols}, source_id) "
                           f"VALUES (:sid, :p, {vals}, :src) ON DUPLICATE KEY UPDATE {upd}, source_id = VALUES(source_id)"), rows)
    return {"source_id": source_id, "new_rows": n_new, "duplicates_found": n_dup,
            "duplicates_action": on_duplicate, "written": len(rows)}


def existing_overlap(df: pd.DataFrame) -> int:
    """How many (state, month) pairs in the upload already exist in MySQL."""
    try:
        cur = run_query("SELECT st.state_name AS state, p.period_month AS period FROM power_supply_monthly p "
                        "JOIN states st ON st.state_id = p.state_id")
    except Exception:  # noqa: BLE001
        return 0
    if cur.empty:
        return 0
    cur["period"] = pd.to_datetime(cur["period"])
    return int(df.merge(cur, on=["state", "period"]).shape[0])


_NAME = re.compile(r"(?m)^-- name:\s*(\S+)\s*$")


def load_sql_library() -> list[dict]:
    """Parse sql/*.sql (except schema.sql) into [{file, name, title, feature, sql}] using '-- name:' blocks."""
    lib = []
    for f in sorted(SQL_DIR.glob("*.sql")):
        if f.name == "schema.sql":
            continue
        parts = _NAME.split(f.read_text(encoding="utf-8"))
        for name, body in zip(parts[1::2], parts[2::2]):
            meta = {m.group(1): m.group(2).strip() for m in re.finditer(r"(?m)^-- (title|feature):\s*(.*)$", body)}
            code = "\n".join(l for l in body.splitlines() if not re.match(r"-- (title|feature):", l)).strip().rstrip(";")
            lib.append({"file": f.name, "name": name, "title": meta.get("title", name),
                        "feature": meta.get("feature", ""), "sql": code})
    return lib
