"""DB tests that need no live MySQL: error handling, SQL file parsing and static SQL checks."""
import re
import pytest

pytest.importorskip("sqlalchemy")
from src import database as db  # noqa: E402
from src.config import SQL_DIR  # noqa: E402


def test_connection_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "1")            # nothing listens here
    monkeypatch.setattr(db, "_engine", None)
    ok, msg = db.test_connection()
    assert ok is False and isinstance(msg, str) and msg


def test_database_url_reads_streamlit_secrets(monkeypatch):
    for name in ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(db.st, "secrets", {
        "DB_USER": "cloud_user",
        "DB_PASSWORD": "cloud_password",
        "DB_HOST": "mysql.example.com",
        "DB_PORT": 3307,
        "DB_NAME": "cloud_db",
    })

    url = db._url()

    assert url.username == "cloud_user"
    assert url.password == "cloud_password"
    assert url.host == "mysql.example.com"
    assert url.port == 3307
    assert url.database == "cloud_db"


def test_sql_library_parses_all_required_techniques():
    lib = db.load_sql_library()
    text = " ".join(q["sql"].upper() for q in lib)
    for needle in ["WITH ", "LAG(", "RANK()", "DENSE_RANK()", "ROWS BETWEEN 2 PRECEDING", "UNBOUNDED PRECEDING", "JOIN "]:
        assert needle in text, needle
    assert len({q["name"] for q in lib}) == len(lib)          # unique query names
    assert all(q["sql"] and not q["sql"].rstrip().endswith(";") for q in lib)


def test_sql_files_have_no_bind_or_format_hazards():
    for q in db.load_sql_library():
        assert "%" not in q["sql"], q["name"]


def test_schema_has_constraints():
    s = (SQL_DIR / "schema.sql").read_text().upper()
    for needle in ["PRIMARY KEY", "FOREIGN KEY", "UNIQUE (STATE_ID, PERIOD_MONTH)", "CHECK", "INDEX"]:
        assert needle in s


def test_duplicate_import_protection_rejects_in_file_duplicates():
    import pandas as pd
    df = pd.DataFrame({"state": ["A", "A"], "region": ["Northern"] * 2,
                       "period": pd.to_datetime(["2020-04-01"] * 2), "energy_requirement_mu": [1.0, 2.0]})
    with pytest.raises(ValueError):
        db.import_power_supply(df, {}, "skip")
