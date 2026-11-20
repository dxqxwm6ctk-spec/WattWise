"""Power factor in the load signature (NILM-lite) and the rule-based reading of the goal."""

import math

import pytest

from backend import actions, agent, config, db, goal, nilm


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


# ---------- power factor math ----------

def test_reactive_power_from_pf():
    assert nilm.reactive(100, 1.0) == pytest.approx(0)
    assert nilm.reactive(80, 0.8) == pytest.approx(60)          # 3-4-5 triangle
    assert nilm.reactive(100, None) is None


def test_step_pf_of_a_jump():
    assert nilm.step_pf(80, 60) == 0.8
    assert nilm.step_pf(40, 0) == 1.0
    assert nilm.step_pf(40, None) is None


def test_pf_tells_lamp_from_fan_with_almost_the_same_watts():
    lamp = {"id": "lamp", "signature_w": 40, "signature_pf": 1.0}
    fan = {"id": "fan", "signature_w": 45, "signature_pf": 0.8}
    # A 41 W jump: watts alone say "lamp", but its reactive part says "fan".
    d_q = nilm.reactive(41, 0.8)
    best, _ = nilm.match(41, d_q, [lamp, fan])
    assert best["id"] == "fan"
    best, _ = nilm.match(41, None, [lamp, fan])                # no PF -> watts only
    assert best["id"] == "lamp"


def test_load_type_labels():
    assert "مقاومي" in nilm.load_type_ar(0.99)
    assert "محرّك" in nilm.load_type_ar(0.8)


# ---------- the agent learns the PF when the meter verifies an action ----------

def _reading(power_w, q_var, bedroom_occupied=False):
    pf = power_w / math.hypot(power_w, q_var)
    return {
        "site": "home", "source": "simulator",
        "meter": {"power_w": power_w, "energy_kwh": 100.0, "pf": round(pf, 4)},
        "rooms": [{"room_id": r, "temp_c": 25.0, "light": 1200,
                   "occupied": bedroom_occupied if r == "bedroom" else r in ("living", "kids", "kitchen"),
                   "window_open": r == "bedroom"}
                  for r in ("living", "bedroom", "kids", "kitchen", "bath", "hall")],
    }


def test_verified_action_stores_the_step_pf(conn):
    ac_q = nilm.reactive(980, 0.85)
    actions.set_goal(conn, "home", "keep the bill under 30 JD", 30)
    actions.ingest(conn, _reading(2500, 500 + ac_q))
    agent.tick(conn, "home")
    agent.tick(conn, "home")
    a = actions.pending_approval(conn, "home")
    assert a and a["device_id"] == "bedAc"
    actions.approve(conn, "home", a["id"])
    # The "before" reading sits inside the 3 s before the approval, not in the 1.5 s "after" window.
    conn.execute("UPDATE meter_readings SET ts=ts-2")
    actions.ingest(conn, _reading(1520, 500))
    agent.tick(conn, "home")
    d = db.device(conn, "home", "bedAc")
    assert d["agent_off"] == actions.AGENT_OFF_VERIFIED
    assert d["signature_pf"] == pytest.approx(0.85, abs=0.03)


def test_old_database_gets_the_new_columns(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE meter_readings (id INTEGER PRIMARY KEY, site TEXT, ts REAL, meter_ts REAL, "
                "source TEXT, power_w REAL, baseline_w REAL, energy_kwh REAL, voltage_v REAL, "
                "current_a REAL, freq_hz REAL)")
    old.commit()
    old.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    db.init_db()
    with db.connect() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(meter_readings)")}
    assert "pf" in cols


# ---------- the goal decides the plan ----------

def test_percent_is_not_read_as_dinars():
    from backend.assistant import read_goal
    assert read_goal("نزّل الاستهلاك 15% هالأسبوع") is None
    assert read_goal("الفاتورة تحت 25 دينار") == 25
    assert goal.read_percent("نزّل ١٥ بالمية") == 15


def test_different_goals_give_different_plans(conn):
    actions.set_goal(conn, "home", "نزّل استهلاك غرفة النوم 15% هالأسبوع بدون ما نحس بالحر", None)
    p1 = db.get_state(conn, "plan:home")
    actions.set_goal(conn, "home", "بدي الفاتورة ما تتعدى ٢٥ دينار", None)
    p2 = db.get_state(conn, "plan:home")
    assert p1["steps"] != p2["steps"]
    assert p1["focus"]["rooms"] == ["bedroom"] and p1["intent"]["percent"] == 15 and p1["intent"]["comfort"]
    assert any("15٪" in s for s in p1["steps"]) and any("غرفة النوم" in s for s in p1["steps"])
    assert p2["intent"]["bill_jd"] == 25 and not p2["focus"]["rooms"]


def test_focus_from_the_goal_orders_the_waste(conn):
    # Lights only: the empty bedroom's AC is bigger, but the goal is about lights.
    actions.set_goal(conn, "home", "طفّي الإنارة الزايدة", None)
    conn.execute("UPDATE devices SET is_on=1 WHERE site='home' AND id='bedLight'")
    actions.ingest(conn, _reading(2500, 600))
    wastes = agent.detect_waste(conn, "home", __import__("time").time())
    assert wastes[0]["device"]["kind"] == "light"


def test_office_number_must_stand_alone(conn):
    intent = goal.understand(conn, "building", "خفّف مكتب 2 بنسبة 10%", None)
    assert [r["id"] for r in intent["rooms"]] == ["office2"]
    intent = goal.understand(conn, "building", "خفّف المبنى 15%", None)
    assert intent["rooms"] == []
