"""SQLite storage shared by the FastAPI backend and the MCP server.

SQLite is a deliberate choice: single user, single file, zero ops, and both
processes can open it (WAL mode) through a shared Docker volume.
"""
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,              -- ISO datetime (local)
    source TEXT NOT NULL,          -- withings | tanita | apple_health | demo
    metric TEXT NOT NULL,          -- weight_kg, body_fat_pct, muscle_mass_kg, ...
    value REAL NOT NULL,
    unit TEXT,
    UNIQUE(ts, source, metric)
);
CREATE INDEX IF NOT EXISTS ix_meas_metric_ts ON measurements(metric, ts);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    start_ts TEXT NOT NULL,
    end_ts TEXT,
    source TEXT NOT NULL,          -- apple_health | kinetix | demo
    type TEXT NOT NULL,            -- strength, running, cycling, yoga, ...
    duration_min REAL,
    kcal REAL,
    distance_km REAL,
    avg_hr REAL,
    details TEXT,                  -- JSON (exercises, sets, ...)
    UNIQUE(start_ts, source, type)
);

CREATE TABLE IF NOT EXISTS cycle_days (
    date TEXT PRIMARY KEY,         -- YYYY-MM-DD with recorded menstrual flow
    flow TEXT NOT NULL,            -- light | medium | heavy | unspecified
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    meal TEXT NOT NULL,            -- breakfast | lunch | dinner | snack
    name TEXT NOT NULL,
    kcal REAL, carbs_g REAL, fat_g REAL, protein_g REAL, fiber_g REAL,
    source TEXT NOT NULL,          -- foodvisor_vision | demo | manual
    UNIQUE(date, meal, name)
);

CREATE TABLE IF NOT EXISTS weather (
    date TEXT PRIMARY KEY,
    tmax REAL, tmin REAL, precip_mm REAL, wind_max REAL, weather_code INTEGER
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT NOT NULL,
    metric TEXT,                   -- measurement metric to track (optional)
    baseline_value REAL,
    target_value REAL,
    unit TEXT,
    deadline TEXT,
    weekly_plan TEXT,              -- JSON list of strings
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    provider TEXT PRIMARY KEY,
    access_token TEXT, refresh_token TEXT, expires_at REAL, user_id TEXT
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    model TEXT, input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL
);
"""


def db_path() -> str:
    path = get_settings().abs_path(get_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def rows(sql: str, params: tuple | dict = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def upsert_measurements(records: list[dict]) -> int:
    """records: {ts, source, metric, value, unit}"""
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO measurements(ts, source, metric, value, unit) "
            "VALUES(:ts, :source, :metric, :value, :unit)",
            records,
        )
    return len(records)


def upsert_workouts(records: list[dict]) -> int:
    for r in records:
        r.setdefault("end_ts", None)
        r.setdefault("kcal", None)
        r.setdefault("distance_km", None)
        r.setdefault("avg_hr", None)
        r["details"] = json.dumps(r.get("details") or {})
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO workouts(start_ts, end_ts, source, type, duration_min, kcal, "
            "distance_km, avg_hr, details) VALUES(:start_ts, :end_ts, :source, :type, :duration_min, "
            ":kcal, :distance_km, :avg_hr, :details)",
            records,
        )
    return len(records)


def upsert_cycle_days(records: list[dict]) -> int:
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cycle_days(date, flow, source) VALUES(:date, :flow, :source)",
            records,
        )
    return len(records)


def upsert_meals(records: list[dict]) -> int:
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO meals(date, meal, name, kcal, carbs_g, fat_g, protein_g, fiber_g, source) "
            "VALUES(:date, :meal, :name, :kcal, :carbs_g, :fat_g, :protein_g, :fiber_g, :source)",
            records,
        )
    return len(records)
