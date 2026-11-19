"""Anomaly detection: learn the normal residual, flag an unknown load, clear it, never act."""

import pytest

from backend import actions, anomaly, config, db
from tests.test_flow import reading


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    with db.connect() as c:
        yield c


def expected(conn):
    return anomaly.expected_w(conn, "home")


def feed(conn, extra_w, n, start=0):
    """n readings at 'what the devices explain' + a small wobble + extra_w."""
    base = expected(conn)
    for i in range(n):
        r = reading(base + 40 + (i % 5) * 8 + extra_w)
        r["meter_ts"] = 1_700_000_000 + start + i
        actions.ingest(conn, r)


def test_no_alert_while_learning(conn):
    feed(conn, 2000, anomaly.WARMUP_SAMPLES - 1)
    assert not anomaly.status(conn, "home")["open"]


def test_unknown_load_raises_one_alert_then_clears(conn):
    feed(conn, 0, 60)
    assert anomaly.status(conn, "home")["ready"]
    feed(conn, 0, 30, start=60)
    assert not anomaly.status(conn, "home")["open"]       # normal wobble is not an anomaly

    feed(conn, 700, anomaly.CONFIRM_READINGS - 1, start=100)
    assert not anomaly.status(conn, "home")["open"]       # a short spike is not enough
    feed(conn, 700, 10, start=110)
    st = anomaly.status(conn, "home")
    assert st["open"] and st["kind"] == "extra" and 600 < st["residual_w"] < 800

    events = [r["event"] for r in db.rows(conn.execute("SELECT event FROM audit_log"))]
    assert events.count("anomaly") == 1                   # one alert, not one per second

    feed(conn, 0, 10, start=130)
    assert not anomaly.status(conn, "home")["open"]
    events = [r["event"] for r in db.rows(conn.execute("SELECT event FROM audit_log"))]
    assert "anomaly_cleared" in events


def test_anomaly_is_not_learned_as_normal(conn):
    feed(conn, 0, 60)
    before = anomaly.band(conn, "home", 0, True) or anomaly.band(conn, "home", 0, False)
    feed(conn, 700, 200, start=100)
    s = anomaly._stats(conn, "home", "all")
    assert abs(s["mean"] - before["mean"]) < 20


def test_missing_load_is_flagged(conn):
    feed(conn, 0, 60)
    feed(conn, -900, 10, start=100)   # e.g. the living-room AC unplugged while marked on
    assert anomaly.status(conn, "home")["kind"] == "missing"


def test_alert_switches_nothing(conn):
    before = [(d["id"], d["is_on"]) for d in db.devices(conn, "home")]
    feed(conn, 0, 60)
    feed(conn, 700, 10, start=100)
    assert [(d["id"], d["is_on"]) for d in db.devices(conn, "home")] == before
    assert actions.pending_approval(conn, "home") is None


def test_no_check_while_measuring_a_new_device(conn):
    feed(conn, 0, 60)
    db.set_state(conn, "learn:home", {"device_id": "x", "status": "measuring"})
    feed(conn, 1800, 10, start=100)
    assert not anomaly.status(conn, "home")["open"]
