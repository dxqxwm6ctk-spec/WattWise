"""End-to-end agent flow on a temporary database: waste -> proposal -> approve / reject / silence."""

import time

import pytest

from backend import actions, agent, config, db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "WASTE_EMPTY_S", 0)
    monkeypatch.setattr(config, "ANALYZE_S", 0)
    monkeypatch.setattr(config, "VERIFY_AFTER_S", 0)
    agent._analyzing.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def reading(power_w, bedroom_occupied=True, window=False):
    return {
        "site": "home", "source": "simulator",
        "meter": {"power_w": power_w, "energy_kwh": 100.0},
        "rooms": [
            {"room_id": r, "temp_c": 25.0, "light": 1200,
             "occupied": bedroom_occupied if r == "bedroom" else r in ("living", "kids", "kitchen"),
             "window_open": window and r == "bedroom"}
            for r in ("living", "bedroom", "kids", "kitchen", "bath", "hall")
        ],
    }


def make_waste(conn):
    actions.set_goal(conn, "home", "keep the bill under 30 JD", 30)
    actions.ingest(conn, reading(2500, bedroom_occupied=False, window=True))
    agent.tick(conn, "home")          # detects waste -> analyzing
    agent.tick(conn, "home")          # proposes -> pending
    return actions.pending_approval(conn, "home")


def test_no_goal_means_no_proposal(conn):
    actions.ingest(conn, reading(2500, bedroom_occupied=False))
    agent.tick(conn, "home")
    agent.tick(conn, "home")
    assert actions.pending_approval(conn, "home") is None


def test_waste_creates_approval_for_bedroom_ac(conn):
    a = make_waste(conn)
    assert a is not None and a["device_id"] == "bedAc"
    assert db.device(conn, "home", "bedAc")["is_on"] == 1   # nothing happened yet


def test_reject_means_no_action(conn):
    a = make_waste(conn)
    actions.reject(conn, "home", a["id"])
    assert db.device(conn, "home", "bedAc")["is_on"] == 1
    agent.tick(conn, "home")
    agent.tick(conn, "home")
    assert actions.pending_approval(conn, "home") is None    # cooldown: does not nag


def test_silence_means_no_action(conn):
    a = make_waste(conn)
    agent.tick(conn, "home", now=a["created_ts"] + config.APPROVAL_TIMEOUT_S + 1)
    row = db.one(conn.execute("SELECT status FROM approvals WHERE id=?", (a["id"],)))
    assert row["status"] == actions.EXPIRED
    assert db.device(conn, "home", "bedAc")["is_on"] == 1
    with pytest.raises(actions.ActionError):
        actions.approve(conn, "home", a["id"])


def test_approve_switches_off_and_meter_verifies(conn):
    a = make_waste(conn)
    actions.approve(conn, "home", a["id"])
    assert db.device(conn, "home", "bedAc")["is_on"] == 0
    actions.ingest(conn, reading(1500, bedroom_occupied=False, window=True))
    # Only the new, lower reading counts as "after".
    conn.execute("UPDATE meter_readings SET ts=ts-10 WHERE id=(SELECT MIN(id) FROM meter_readings)")
    agent.tick(conn, "home")
    d = db.device(conn, "home", "bedAc")
    assert d["agent_off"] == actions.AGENT_OFF_VERIFIED
    assert d["signature_measured"] == 1


def test_estop_cancels_and_restores(conn):
    a = make_waste(conn)
    actions.approve(conn, "home", a["id"])
    actions.emergency_stop(conn, "home")
    assert db.device(conn, "home", "bedAc")["is_on"] == 1
    assert actions.flag(conn, "estop", "home")
    agent.tick(conn, "home")
    agent.tick(conn, "home")
    assert actions.pending_approval(conn, "home") is None


def test_human_cannot_switch_critical_load(conn):
    with pytest.raises(actions.ActionError):
        actions.human_toggle(conn, "home", "fridge", False)
    assert db.device(conn, "home", "fridge")["is_on"] == 1


def test_router_off_enters_safe_mode(conn):
    with pytest.raises(actions.ActionError):
        actions.human_toggle(conn, "home", "router", False)           # needs confirmation
    actions.human_toggle(conn, "home", "router", False, confirmed=True)
    assert actions.flag(conn, "safe_mode", "home")


def test_stale_data_goes_fail_safe(conn):
    a = make_waste(conn)
    actions.approve(conn, "home", a["id"])
    agent.tick(conn, "home", now=time.time() + config.STALE_READING_S + 5)
    assert db.device(conn, "home", "bedAc")["is_on"] == 1
    assert actions.flag(conn, "fault", "home")
