"""Versioned SQLite storage. Every account-owned query must include user_id."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = {"budget_min": None, "bathrooms_min": 0, "floor_min": None, "exclude_occupied": False, "metro_stations": [], "search_bounds": [], "name": "Minha primeira casa", "budget_max": 330000, "area_min": 35,
    "area_max": 70, "bedrooms_min": 2, "parking_min": 0, "metro_max": 15,
    "condo_max": None, "monthly_max": 580, "cities": ["São Paulo"], "neighborhoods": [],
    "require_elevator": False, "weights": {"price": 40, "location": 35, "quality": 25},
    "alert_drop_percent": 5, "exclude_unknown_required": False}

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL COLLATE NOCASE,
 name TEXT NOT NULL, password_hash TEXT NOT NULL, profile TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 name TEXT NOT NULL, kind TEXT NOT NULL, url TEXT, enabled INTEGER NOT NULL DEFAULT 0,
 authorized INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
 last_attempt TEXT, last_success TEXT, error TEXT, created_at TEXT NOT NULL,
 UNIQUE(user_id,name,kind));
CREATE TABLE IF NOT EXISTS properties(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 source_id INTEGER REFERENCES sources(id), source TEXT NOT NULL, external_id TEXT NOT NULL,
 data TEXT NOT NULL, first_seen TEXT, last_seen TEXT, imported_at TEXT NOT NULL,
 canonical_key TEXT NOT NULL, UNIQUE(user_id,source,external_id));
CREATE INDEX IF NOT EXISTS properties_user ON properties(user_id,id);
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL REFERENCES properties(id),
 price REAL NOT NULL, observed_at TEXT, recorded_at TEXT NOT NULL, fingerprint TEXT NOT NULL,
 UNIQUE(property_id,fingerprint));
CREATE INDEX IF NOT EXISTS observations_property ON observations(property_id,id);
CREATE TABLE IF NOT EXISTS tracking(user_id INTEGER NOT NULL REFERENCES users(id),
 property_id INTEGER NOT NULL REFERENCES properties(id), saved INTEGER NOT NULL DEFAULT 0,
 stage TEXT NOT NULL DEFAULT 'saved', notes TEXT NOT NULL DEFAULT '', visit_at TEXT,
 checklist TEXT NOT NULL DEFAULT '{}', assessments TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL,
 PRIMARY KEY(user_id,property_id));
CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 records TEXT NOT NULL, errors TEXT NOT NULL, warnings TEXT NOT NULL, created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL, committed_result TEXT);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 property_id INTEGER REFERENCES properties(id), kind TEXT NOT NULL, title TEXT NOT NULL,
 body TEXT NOT NULL, created_at TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0,
 dedupe_key TEXT NOT NULL, UNIQUE(user_id,dedupe_key));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 source_id INTEGER REFERENCES sources(id), started_at TEXT NOT NULL, finished_at TEXT,
 status TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '{}', error TEXT);
CREATE TABLE IF NOT EXISTS locks(name TEXT PRIMARY KEY, expires_at TEXT NOT NULL, owner TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runtime(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS daily_runs(source_id INTEGER NOT NULL REFERENCES sources(id), day TEXT NOT NULL,
 status TEXT NOT NULL, PRIMARY KEY(source_id,day));
CREATE TABLE IF NOT EXISTS login_limits(key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, until_at TEXT NOT NULL);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def db_path() -> Path:
    return Path(os.environ.get("IMOVEL_DB_PATH", str(ROOT / "data" / "radar.sqlite3"))).resolve()


def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def initialize():
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 3:
            raise RuntimeError("Database schema is newer than this application")
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO schema_versions VALUES(1,?)", (now_iso(),))
        columns = {row[1] for row in conn.execute('PRAGMA table_info(tracking)')}
        if 'assessments' not in columns:
            conn.execute("ALTER TABLE tracking ADD COLUMN assessments TEXT NOT NULL DEFAULT '{}'")
        conn.execute("INSERT OR IGNORE INTO schema_versions VALUES(2,?)", (now_iso(),))
        conn.executescript("""
CREATE TABLE IF NOT EXISTS saved_searches(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 name TEXT NOT NULL, profile TEXT NOT NULL, q TEXT NOT NULL DEFAULT '', construction TEXT NOT NULL DEFAULT 'all',
 enabled INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS saved_searches_user ON saved_searches(user_id,id);
CREATE TABLE IF NOT EXISTS saved_search_matches(search_id INTEGER NOT NULL REFERENCES saved_searches(id),
 canonical_key TEXT NOT NULL, property_id INTEGER NOT NULL REFERENCES properties(id), first_matched_at TEXT NOT NULL,
 PRIMARY KEY(search_id,canonical_key));
""")
        alert_columns = {row[1] for row in conn.execute('PRAGMA table_info(alerts)')}
        if 'saved_search_id' not in alert_columns:
            conn.execute("ALTER TABLE alerts ADD COLUMN saved_search_id INTEGER REFERENCES saved_searches(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS alerts_search_user ON alerts(user_id,saved_search_id,id)")
        conn.execute("INSERT OR IGNORE INTO schema_versions VALUES(3,?)", (now_iso(),))
        conn.execute("PRAGMA user_version=3")
        conn.execute("UPDATE sources SET enabled=0,authorized=0 WHERE kind='portal' AND name IN ('OLX','VivaReal')")
        from .cost_migration import repair_portal_cost_periods
        repair_portal_cost_periods(conn)


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def load_property(row):
    from .construction import construction_status
    value = json.loads(row["data"])
    value["construction_status"] = construction_status(value)
    value.update(id=row["id"], source=row["source"], external_id=row["external_id"],
        first_seen=row["first_seen"], last_seen=row["last_seen"], imported_at=row["imported_at"],
        canonical_key=row["canonical_key"])
    return value
