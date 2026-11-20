"""Home EV charger: session recognition, measured energy, smart-charging rules."""

import time
from datetime import datetime

import pytest

from backend import actions, agent, config, db, ev


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "VERIFY_AFTER_S", 0)
    agent._analyzing.clear()
    db.init_db()
    with db.connect() as c:
        yield c


ROOMS = ("living", "bedroom", "kids", "kitchen", "bath", "hall", "garage")


def ts_at(hour, minute=0):
    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def reading(meter_ts, power_w, soc=30.0, kwh=100.0):
    return {"site": "home", "source": "simulator", "meter_ts": meter_ts,
            "meter": {"power_w": power_w, "energy_kwh": kwh},
            "rooms": [{"room_id": r, "temp_c": 25.0, "occupied": r in ("living", "kids"), "window_open": False}
                      for r in ROOMS],
            "ev": {"soc_pct": soc, "plugged": True}}


def test_session_is_recognised_by_its_step_and_measured(conn):
    t = ts_at(14)
    actions.ingest(conn, reading(t, 1500))
    ev.track(conn, "home", time.time())                       # charger off: remembers the house load
    db.set_device(conn, "home", "evCharger", is_on=1)
    actions.ingest(conn, reading(t + 60, 1500 + 7350))
    ev.track(conn, "home", time.time())
    sess = db.get_state(conn, "ev_session:home")
    assert sess and abs(sess["step_w"] - 7350) < 1
    for minute in range(1, 61):                                # one hour, a reading every minute
        actions.ingest(conn, reading(t + 60 + minute * 60, 1500 + 7350, soc=30 + minute / 5))
        ev.track(conn, "home", time.time())
    assert db.get_state(conn, "ev_session:home")["kwh"] == pytest.approx(7.35, abs=0.01)


def test_a_step_that_does_not_match_is_not_a_charging_session(conn):
    t = ts_at(14)
    actions.ingest(conn, reading(t, 1500))
    ev.track(conn, "home", time.time())
    db.set_device(conn, "home", "evCharger", is_on=1)
    actions.ingest(conn, reading(t + 60, 1500 + 900))         # +900 W is not a 7.4 kW charger
    ev.track(conn, "home", time.time())
    assert db.get_state(conn, "ev_session:home") is None


def test_night_plan_only_when_the_car_is_still_ready_in_time():
    t = ts_at(20)
    ok = ev.night_plan("home", t, soc=30, power_w=7400)       # needs ~4 h, 00:00-07:00 gives 7 h
    assert ok and ok["resume_at"] == "00:00" and ok["need_min"] <= ok["window_min"]
    assert ev.night_plan("home", t, soc=0, power_w=3000) is None   # needs ~13 h: never propose


def test_smart_charging_asks_the_human_and_resumes_by_timer(conn):
    actions.set_goal(conn, "home", "reduce consumption", None)
    t = ts_at(20)
    actions.ingest(conn, reading(t, 2500))
    ev.track(conn, "home", time.time())
    db.set_device(conn, "home", "evCharger", is_on=1)
    actions.ingest(conn, reading(t + 60, 2500 + 7400))
    agent.tick(conn, "home")
    p = actions.pending_approval(conn, "home")
    assert p and p["device_id"] == "evCharger" and p["turn_on"] == 0
    actions.approve(conn, "home", p["id"])
    timers = conn.execute("SELECT * FROM timers WHERE site='home' AND device_id='evCharger'").fetchall()
    assert len(timers) == 1 and timers[0]["turn_on"] == 1


def test_no_smart_charging_proposal_outside_the_evening_peak(conn):
    actions.set_goal(conn, "home", "reduce consumption", None)
    t = ts_at(14)
    actions.ingest(conn, reading(t, 2500))
    ev.track(conn, "home", time.time())
    db.set_device(conn, "home", "evCharger", is_on=1)
    actions.ingest(conn, reading(t + 60, 2500 + 7400))
    agent.tick(conn, "home")
    assert actions.pending_approval(conn, "home") is None


def test_a_paused_charge_is_not_counted_as_a_saving(conn):
    t = ts_at(20)
    db.set_device(conn, "home", "evCharger", is_on=0, agent_off=actions.AGENT_OFF_VERIFIED)
    actions.ingest(conn, reading(t, 2500))
    actions.ingest(conn, reading(t + 3600, 2500))
    assert db.get_state(conn, "saved_wh:home", 0.0) == 0.0
