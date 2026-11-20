"""SQLite storage. One small file, plain SQL, no ORM."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from backend import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    site        TEXT NOT NULL,
    id          TEXT NOT NULL,
    name        TEXT NOT NULL,
    PRIMARY KEY (site, id)
);

CREATE TABLE IF NOT EXISTS devices (
    site        TEXT    NOT NULL,
    id          TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    room        TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    rated_w     REAL    NOT NULL,          -- nameplate guess
    tier        TEXT    NOT NULL,          -- T1 (needs approval) or T2 (critical, forbidden)
    sensitive   INTEGER NOT NULL DEFAULT 0,
    allow       INTEGER NOT NULL DEFAULT 1, -- on the agent allowlist?
    is_on       INTEGER NOT NULL,          -- desired relay state
    normal_on   INTEGER NOT NULL,          -- state to return to on emergency stop / fail-safe
    setpoint    REAL,                      -- AC only
    signature_w REAL    NOT NULL,          -- load signature (step in watts)
    signature_measured INTEGER NOT NULL DEFAULT 0,
    agent_off   INTEGER NOT NULL DEFAULT 0, -- 1 while the agent holds it off after an approval
    energy_wh   REAL    NOT NULL DEFAULT 0, -- attributed energy (NILM-lite)
    added       INTEGER NOT NULL DEFAULT 0, -- added by the user from the app
    relay_channel INTEGER,
    PRIMARY KEY (site, id)
);

CREATE TABLE IF NOT EXISTS meter_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    ts          REAL    NOT NULL,          -- server time when received
    meter_ts    REAL    NOT NULL,          -- device/simulator clock (simulator runs faster)
    source      TEXT    NOT NULL,          -- 'device' or 'simulator'
    power_w     REAL    NOT NULL,
    baseline_w  REAL    NOT NULL,          -- expected power without the agent's actions
    energy_kwh  REAL,
    voltage_v   REAL,
    current_a   REAL,
    freq_hz     REAL
);
CREATE INDEX IF NOT EXISTS idx_meter_site_ts ON meter_readings(site, ts);

CREATE TABLE IF NOT EXISTS room_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    room_id     TEXT    NOT NULL,
    ts          REAL    NOT NULL,
    temp_c      REAL,
    humidity    REAL,
    light       REAL,                      -- raw LDR value 0..4095
    occupied    INTEGER,                   -- PIR: 1 occupied, 0 empty (no cameras)
    window_open INTEGER                    -- simulated door/window contact
);
CREATE INDEX IF NOT EXISTS idx_room_site_ts ON room_readings(site, room_id, ts);

CREATE TABLE IF NOT EXISTS approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    device_id   TEXT    NOT NULL,
    turn_on     INTEGER NOT NULL,
    created_ts  REAL    NOT NULL,
    expires_ts  REAL    NOT NULL,
    title       TEXT    NOT NULL,
    reason      TEXT    NOT NULL,          -- plain Arabic explanation
    details     TEXT,                      -- JSON with the numbers
    status      TEXT    NOT NULL,          -- pending/approved/rejected/expired/blocked/cancelled
    decided_ts  REAL,
    power_before REAL,
    power_after  REAL,
    verified_ts  REAL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    ts          REAL    NOT NULL,
    clock       TEXT,                      -- HH:MM on the site clock, for display
    tier        TEXT    NOT NULL,          -- T0 / T1 / T2 / OK / STOP / MANUAL
    actor       TEXT    NOT NULL,          -- agent / human / policy / system
    event       TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    details     TEXT
);

CREATE TABLE IF NOT EXISTS goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    created_ts  REAL    NOT NULL,
    text        TEXT    NOT NULL,
    bill_target_jd REAL,
    active      INTEGER NOT NULL
);

-- Anomaly model: running mean/variance of (meter - expected) per hour and occupancy.
CREATE TABLE IF NOT EXISTS anomaly_stats (
    site        TEXT NOT NULL,
    bucket      TEXT NOT NULL,             -- "19:occ", "03:empty", or "all"
    n           INTEGER NOT NULL,
    mean        REAL NOT NULL,
    m2          REAL NOT NULL,
    PRIMARY KEY (site, bucket)
);

-- Timers and daily schedules (on/off only). Times are on the site clock.
CREATE TABLE IF NOT EXISTS schedules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    device_id   TEXT    NOT NULL,
    on_time     TEXT,                      -- "HH:MM" or NULL
    off_time    TEXT,                      -- "HH:MM" or NULL
    days        TEXT,                      -- weekdays it runs, "0".."6" (0 = Sunday); NULL = every day
    enabled     INTEGER NOT NULL DEFAULT 1,
    source      TEXT    NOT NULL,          -- user / command / suggested
    created_ts  REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS timers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site        TEXT    NOT NULL,
    device_id   TEXT    NOT NULL,
    turn_on     INTEGER NOT NULL,          -- what happens when the time comes
    due_ts      REAL    NOT NULL,          -- on the site clock (meter_ts)
    minutes     INTEGER NOT NULL,
    created_ts  REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS system_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
"""


@contextmanager
def connect(path: Path | None = None):
    conn = sqlite3.connect(path or config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and seed rooms/devices from config/sites.json (first run only)."""
    # On a cloud host the database may live on a mounted volume (for example /data).
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Older databases were made before schedules had days: add the column.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(schedules)")}
        if "days" not in cols:
            conn.execute("ALTER TABLE schedules ADD COLUMN days TEXT")
        for site_id, site in config.load_sites().items():
            for room in site["rooms"]:
                conn.execute("INSERT OR IGNORE INTO rooms (site, id, name) VALUES (?,?,?)",
                             (site_id, room["id"], room["name"]))
            for d in site["devices"]:
                on = int(d.get("on", True))
                conn.execute(
                    "INSERT OR IGNORE INTO devices (site, id, name, room, kind, rated_w, tier, sensitive, "
                    "allow, is_on, normal_on, setpoint, signature_w, relay_channel) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (site_id, d["id"], d["name"], d["room"], d["kind"], d["rated_w"], d["tier"],
                     int(d.get("sensitive", False)), int(d.get("allow", d["tier"] == "T1")),
                     on, on, d.get("setpoint"), d["rated_w"], d.get("relay_channel")),
                )


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def one(cursor) -> dict | None:
    r = cursor.fetchone()
    return dict(r) if r else None


# --- system state (small key/value store) ---

def get_state(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_state(conn, key: str, value) -> None:
    conn.execute(
        "INSERT INTO system_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


# --- audit log ---

def site_clock(conn, site: str) -> str:
    row = conn.execute("SELECT meter_ts FROM meter_readings WHERE site=? ORDER BY id DESC LIMIT 1",
                       (site,)).fetchone()
    t = row["meter_ts"] if row else time.time()
    return time.strftime("%H:%M", time.localtime(t))


def audit(conn, site: str, tier: str, actor: str, event: str, message: str,
          details: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (site, ts, clock, tier, actor, event, message, details) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (site, time.time(), site_clock(conn, site), tier, actor, event, message,
         json.dumps(details or {}, ensure_ascii=False)),
    )


# --- devices / rooms / readings ---

def devices(conn, site: str) -> list[dict]:
    return rows(conn.execute("SELECT * FROM devices WHERE site=? ORDER BY added, rowid", (site,)))


def device(conn, site: str, device_id: str) -> dict | None:
    return one(conn.execute("SELECT * FROM devices WHERE site=? AND id=?", (site, device_id)))


def rooms(conn, site: str) -> list[dict]:
    return rows(conn.execute("SELECT * FROM rooms WHERE site=? ORDER BY rowid", (site,)))


def latest_meter(conn, site: str) -> dict | None:
    return one(conn.execute("SELECT * FROM meter_readings WHERE site=? ORDER BY id DESC LIMIT 1", (site,)))


def latest_room(conn, site: str, room_id: str) -> dict | None:
    return one(conn.execute(
        "SELECT * FROM room_readings WHERE site=? AND room_id=? ORDER BY id DESC LIMIT 1",
        (site, room_id)))


def avg_power(conn, site: str, seconds: float) -> float | None:
    row = conn.execute("SELECT AVG(power_w) AS p FROM meter_readings WHERE site=? AND ts>=?",
                       (site, time.time() - seconds)).fetchone()
    return row["p"]


def set_device(conn, site: str, device_id: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE devices SET {cols} WHERE site=? AND id=?", (*fields.values(), site, device_id))
