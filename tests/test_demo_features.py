"""Judge-demo features: offline mode, goal in percent, live savings counter and the 1000-homes projection."""

import time

import pytest

from backend import actions, agent, config, connectivity, db, impact, llm, state, weather
from tests.test_flow import conn, make_waste, reading  # noqa: F401  (pytest fixture)
from tests.test_llm import FakeProvider


# ---------- offline mode ----------

def test_simulated_offline_is_reported_and_logged(conn):
    actions.ingest(conn, reading(800))
    connectivity.set_forced_offline(True)
    agent.note_internet_changes(conn)
    s = state.build(conn, "home")["internet"]
    assert s["online"] is False and s["forced"] is True
    assert "local_work" in s
    events = [r["event"] for r in db.rows(conn.execute("SELECT event FROM audit_log WHERE site='home'"))]
    assert "internet_lost" in events

    connectivity.set_forced_offline(False)
    agent.note_internet_changes(conn)
    assert state.build(conn, "home")["internet"]["online"] is True
    events = [r["event"] for r in db.rows(conn.execute("SELECT event FROM audit_log WHERE site='home'"))]
    assert "internet_back" in events


def test_real_probe_result_changes_state():
    connectivity.reset_for_tests(online=True)
    connectivity._set(False, time.time())
    assert connectivity.is_online() is False
    assert connectivity.pop_changes()[-1]["online"] is False
    connectivity._set(True, time.time())
    assert connectivity.is_online() is True


def test_offline_switches_llm_to_rules_and_skips_weather(conn, monkeypatch):
    llm.set_provider(FakeProvider(final=("no_action", {})))
    assert llm.status(conn)["mode"] == "llm"
    connectivity.set_forced_offline(True)
    assert llm.status(conn)["mode"] == "rules"
    assert llm.available(conn) is False

    monkeypatch.setattr(config, "WEATHER_ENABLED", True)
    monkeypatch.setattr(weather, "_fetch", lambda: pytest.fail("must not call the internet when offline"))
    assert weather.get_weather()["available"] is False


def test_agent_still_detects_waste_and_acts_offline(conn):
    """The whole loop (detect -> ask -> approve -> relay) works with no internet."""
    connectivity.set_forced_offline(True)
    a = make_waste(conn)
    assert a is not None and a["device_id"] == "bedAc"
    actions.approve(conn, "home", a["id"])
    assert db.device(conn, "home", "bedAc")["is_on"] == 0
    assert actions.commands_for(conn, "home")["relays"]["bedAc"] is False
    work = state.build(conn, "home")["internet"]["local_work"]
    assert work["detections"] >= 1 and work["actions"] == 1


def test_reject_offline_still_means_no_action(conn):
    connectivity.set_forced_offline(True)
    a = make_waste(conn)
    actions.reject(conn, "home", a["id"])
    assert db.device(conn, "home", "bedAc")["is_on"] == 1


# ---------- goal in percent ----------

def test_percent_goal_becomes_bill_target(conn):
    actions.ingest(conn, reading(800))       # energy_kwh = 100 this month
    projected = actions.projected_bill(conn, "home")
    goal = actions.set_goal(conn, "home", "بدي أوفّر ٢٠٪ هالشهر", None)
    assert goal["bill_target_jd"] == pytest.approx(max(1.0, round(projected * 0.8, 1)))
    assert "٢٠" not in str(goal["bill_target_jd"])   # 20% is NOT a 20 JD target
    assert goal["bill_target_jd"] != 20


def test_percent_goal_without_meter_has_no_invented_target(conn):
    goal = actions.set_goal(conn, "home", "وفّر 15%", None)
    assert goal["bill_target_jd"] is None


# ---------- savings counter ----------

def test_no_verified_action_means_zero_savings(conn):
    actions.ingest(conn, reading(800))
    s = state.build(conn, "home")["savings"]
    assert s["kwh"] == 0 and s["today_kwh"] == 0 and s["projection"] is None


def test_today_counter_rolls_over_at_midnight():
    day1 = time.mktime((2026, 11, 20, 23, 0, 0, 0, 0, -1))
    day2 = time.mktime((2026, 11, 21, 0, 30, 0, 0, 0, -1))
    s = impact.add_today(None, day1, 500)
    s = impact.add_today(s, day1 + 60, 250)
    assert impact.today_wh(s, day1) == 750
    assert impact.today_wh(s, day2) == 0
    s = impact.add_today(s, day2, 100)
    assert impact.today_wh(s, day2) == 100


def test_savings_math_and_projection():
    tariff = {"co2_kg_per_kwh": 0.516, "co2_source": "x", "price_source": "y"}
    s = impact.savings(total_wh=2000, today=1000, held_off_w=60, price=0.10, tariff=tariff)
    assert s["jod"] == pytest.approx(0.2)
    assert s["co2_kg"] == pytest.approx(1.032)
    assert s["today_kwh"] == pytest.approx(1.0)
    p = s["projection"]
    assert p["kwh_year"] == 365_000               # 1 kWh/day x 365 x 1000 homes
    assert p["jod_year"] == 36_500
    assert p["co2_t_year"] == pytest.approx(188.3, abs=0.1)


def test_missing_co2_factor_is_not_guessed():
    s = impact.savings(1000, 1000, 0, 0.1, {"co2_kg_per_kwh": None})
    assert s["co2_kg"] is None and s["projection"]["co2_t_year"] is None


def test_verified_action_counts_today(conn):
    t0 = time.time()
    a = make_waste(conn)
    actions.approve(conn, "home", a["id"])
    actions.ingest(conn, {**reading(1500, bedroom_occupied=False, window=True), "meter_ts": t0 + 5})
    conn.execute("UPDATE meter_readings SET ts=ts-10 WHERE id=(SELECT MIN(id) FROM meter_readings)")
    agent.tick(conn, "home")
    assert db.device(conn, "home", "bedAc")["agent_off"] == actions.AGENT_OFF_VERIFIED
    # One simulated hour later the verified device has been held off for an hour.
    actions.ingest(conn, {**reading(1500, bedroom_occupied=False, window=True), "meter_ts": t0 + 5 + 600})
    s = state.build(conn, "home")["savings"]
    assert s["today_kwh"] > 0 and s["kwh"] >= s["today_kwh"]
    assert s["rate_w"] > 0
    assert s["co2_kg"] is not None and s["projection"]["homes"] == 1000
