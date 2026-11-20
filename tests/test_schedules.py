"""Timers, daily schedules, the heater suggestion and plain-Arabic commands.

These touch real loads on a timer, so the Policy Guard rules must hold:
no critical or sensitive loads, the heater never runs more than 3 hours in one
go, and nothing fires during an emergency stop.
"""

import time

import pytest

from backend import actions, agent, assistant, config, db, policy, schedules
from backend.actions import ActionError


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    agent._analyzing.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def at(hhmm: str) -> float:
    """Today's timestamp at hh:mm (local time), like the simulator's clock."""
    h, m = map(int, hhmm.split(":"))
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, 0, 0, 0, -1))


def reading(conn, meter_ts: float, bath_occupied=False):
    actions.ingest(conn, {
        "site": "home", "source": "simulator", "meter_ts": meter_ts,
        "meter": {"power_w": 2000, "energy_kwh": 100.0},
        "rooms": [{"room_id": r, "temp_c": 25.0, "light": 3000,
                   "occupied": r == "bath" and bath_occupied, "window_open": False}
                  for r in ("living", "bedroom", "kids", "kitchen", "bath", "hall")],
    })


def is_on(conn, device_id):
    return bool(db.device(conn, "home", device_id)["is_on"])


# ---------- Policy Guard rules for schedules ----------

def test_critical_and_sensitive_loads_cannot_be_scheduled(conn):
    fridge, router = db.device(conn, "home", "fridge"), db.device(conn, "home", "router")
    assert not policy.check_schedule(fridge, "06:00", "07:00").allowed
    assert not policy.check_timer(fridge, 30).allowed
    assert not policy.check_schedule(router, "01:00", "06:00").allowed
    assert not policy.check_timer(router, 30).allowed


def test_heater_window_longer_than_three_hours_is_refused(conn):
    heater = db.device(conn, "home", "heater")
    assert policy.check_schedule(heater, "05:00", "08:00").allowed          # exactly 3 hours
    assert not policy.check_schedule(heater, "05:00", "08:01").allowed
    assert not policy.check_schedule(heater, "23:00", "02:30").allowed      # across midnight
    with pytest.raises(ActionError):
        schedules.add_schedule(conn, "home", "heater", "05:00", "09:00")


def test_bad_or_short_windows_are_refused(conn):
    lamp = db.device(conn, "home", "livingLight")
    assert not policy.check_schedule(lamp, None, None).allowed
    assert not policy.check_schedule(lamp, "25:00", None).allowed
    assert not policy.check_schedule(lamp, "06:00", "06:05").allowed
    assert not policy.check_timer(lamp, 0).allowed
    assert not policy.check_timer(lamp, 721).allowed


# ---------- they fire on the site clock ----------

def test_timer_switches_off_when_due(conn):
    reading(conn, at("10:00"))
    schedules.add_timer(conn, "home", "tv", 30, turn_on=False)
    reading(conn, at("10:29"))
    agent.tick(conn, "home")
    assert is_on(conn, "tv")
    reading(conn, at("10:30"))
    agent.tick(conn, "home")
    assert not is_on(conn, "tv")
    assert schedules.listing(conn, "home")["timers"] == []


def test_run_for_switches_on_now_and_off_later(conn):
    reading(conn, at("10:00"))
    schedules.add_timer(conn, "home", "washer", 60, turn_on=False, run_now=True)
    assert is_on(conn, "washer")
    reading(conn, at("11:00"))
    agent.tick(conn, "home")
    assert not is_on(conn, "washer")


def test_daily_schedule_fires_when_the_clock_passes(conn):
    reading(conn, at("05:00"))
    agent.tick(conn, "home")                       # first look at the clock
    schedules.add_schedule(conn, "home", "heater", "05:30", "06:30")
    reading(conn, at("05:31"))                     # the simulator jumps a minute per second
    agent.tick(conn, "home")
    assert is_on(conn, "heater")
    reading(conn, at("06:32"))
    agent.tick(conn, "home")
    assert not is_on(conn, "heater")


def test_schedule_runs_only_on_its_days(conn):
    today = schedules.weekday(at("05:00"))
    other = (today + 1) % 7
    reading(conn, at("05:00"))
    agent.tick(conn, "home")
    schedules.add_schedule(conn, "home", "heater", "05:30", "06:30", days=[other])
    reading(conn, at("05:31"))
    agent.tick(conn, "home")
    assert not is_on(conn, "heater")               # not one of its days
    schedules.clear_all(conn, "home")
    schedules.add_schedule(conn, "home", "heater", "05:40", "06:30", days=[today])
    reading(conn, at("05:41"))
    agent.tick(conn, "home")
    assert is_on(conn, "heater")


def test_days_are_checked():
    assert schedules.normalize_days(None) is None
    assert schedules.normalize_days([4, 0, 4]) == "04"
    assert schedules.normalize_days(range(7)) is None            # all week = every day
    with pytest.raises(ActionError):
        schedules.normalize_days([])
    with pytest.raises(ActionError):
        schedules.normalize_days([7])


def test_preview_checks_the_guard_and_saves_nothing(conn):
    p = schedules.preview_schedule(conn, "home", "heater", "05:30", "06:30", [0, 1, 2, 3, 4])
    assert p["room_name"] == "الحمّام" and p["days_text"] == "الأحد للخميس"
    assert schedules.listing(conn, "home")["schedules"] == []
    with pytest.raises(ActionError):
        schedules.preview_schedule(conn, "home", "fridge", "05:30", "06:30")


def test_listing_groups_devices_by_room_for_each_site(conn):
    for site in ("home", "building", "lab"):
        a = schedules.listing(conn, site)
        room_ids = {r["id"] for r in a["rooms"]}
        assert a["devices"] and all(d["room"] in room_ids and d["room_name"] for d in a["devices"])
    home = schedules.listing(conn, "home")
    assert {d["id"] for d in home["locked"]} >= {"fridge", "fireAlarm", "router"}
    assert "fridge" not in {d["id"] for d in home["devices"]}


def test_disabled_schedule_does_nothing(conn):
    reading(conn, at("05:00"))
    agent.tick(conn, "home")
    r = schedules.add_schedule(conn, "home", "heater", "05:30", "06:30")
    schedules.set_enabled(conn, "home", r["id"], False)
    reading(conn, at("05:40"))
    agent.tick(conn, "home")
    assert not is_on(conn, "heater")


def test_nothing_fires_during_emergency_stop(conn):
    reading(conn, at("10:00"))
    schedules.add_timer(conn, "home", "tv", 5, turn_on=False)
    actions.emergency_stop(conn, "home")
    reading(conn, at("10:10"))
    agent.tick(conn, "home")
    assert is_on(conn, "tv")
    assert db.one(conn.execute(
        "SELECT 1 AS x FROM audit_log WHERE site='home' AND event='schedule_blocked'")) is not None


def test_reset_clears_timers_and_schedules(conn):
    reading(conn, at("10:00"))
    schedules.add_timer(conn, "home", "tv", 5, turn_on=False)
    schedules.add_schedule(conn, "home", "heater", "05:30", "06:30")
    actions.reset_demo(conn, "home")
    lst = schedules.listing(conn, "home")
    assert lst["timers"] == [] and lst["schedules"] == []


# ---------- smart heater schedule ----------

def test_shower_times_are_read_from_arabic_text():
    assert schedules.shower_times("الصبح ٦ ونص والمسا ٩") == [390, 1260]
    assert schedules.shower_times("7:15") == [435]
    assert schedules.shower_times("ما بعرف") == []


def test_heater_suggestion_heats_the_hour_before_each_shower(conn):
    reading(conn, at("10:00"))
    s = schedules.suggest_heater(conn, "home", "الصبح ٦ ونص والمسا ٩")
    assert [(i["on_time"], i["off_time"]) for i in s["items"]] == [("05:30", "06:30"), ("20:00", "21:00")]
    assert s["total"]["kwh"] == pytest.approx(4.0, abs=0.01)    # 2 kW x 2 hours (expected, not measured)
    assert schedules.listing(conn, "home")["schedules"] == []   # only a proposal
    schedules.apply_heater(conn, "home", s["device_id"], s["items"])
    assert len(schedules.listing(conn, "home")["schedules"]) == 2


def test_heater_apply_refuses_a_long_window(conn):
    with pytest.raises(ActionError):
        schedules.apply_heater(conn, "home", "heater", [{"on_time": "04:00", "off_time": "09:00"}])
    assert schedules.listing(conn, "home")["schedules"] == []


# ---------- goal and commands in plain Arabic ----------

def test_goal_target_is_read_from_the_words(conn):
    assert assistant.read_goal("بدي الفاتورة ما تتعدى ٢٥ دينار") == 25
    assert assistant.read_goal("وفّر قد ما بتقدر") is None
    g = actions.set_goal(conn, "home", "خلّي الفاتورة تحت 28 دينار", None)
    assert g["bill_target_jd"] == 28


def test_command_off_is_parsed_and_runs_only_after_confirm(conn):
    reading(conn, at("10:00"))
    p = assistant.parse_command(conn, "home", "طفّي مكيّف النوم")
    assert [(i["device_id"], i["action"], i["ok"]) for i in p["items"]] == [("bedAc", "off", True)]
    assert is_on(conn, "bedAc")                    # parsing changes nothing
    assistant.run_command(conn, "home", "طفّي مكيّف النوم")
    assert not is_on(conn, "bedAc")


def test_command_on_a_critical_load_is_refused(conn):
    p = assistant.parse_command(conn, "home", "طفّي الثلاجة")
    assert p["items"] and not p["items"][0]["ok"]
    assistant.run_command(conn, "home", "طفّي الثلاجة")
    assert is_on(conn, "fridge")


def test_command_cannot_switch_off_the_router(conn):
    p = assistant.parse_command(conn, "home", "طفّي الراوتر")
    assert p["items"] and not p["items"][0]["ok"]


def test_command_timer_and_schedule(conn):
    reading(conn, at("10:00"))
    p = assistant.parse_command(conn, "home", "طفّي مكيّف الصالون بعد نص ساعة")
    assert p["items"][0]["action"] == "timer" and p["items"][0]["minutes"] == 30
    p = assistant.parse_command(conn, "home", "سخّان الماء يشتغل من 6 لل 7")
    assert p["items"][0]["action"] == "schedule"
    assert (p["items"][0]["on_time"], p["items"][0]["off_time"]) == ("06:00", "07:00")


def test_unclear_command_asks_instead_of_guessing(conn):
    assert assistant.parse_command(conn, "home", "شو الأخبار")["items"] == []
    assert assistant.parse_command(conn, "home", "طفّي الإشي")["items"] == []


def test_why_and_weekly_report_use_measured_numbers(conn):
    reading(conn, at("10:00"))
    w = assistant.why_bill(conn, "home")
    assert w["headline"] and w["causes"]
    text = assistant.weekly_report(conn, "home")
    assert "التقرير الأسبوعي" in text and "لسا ما في توفير مُقاس" in text
