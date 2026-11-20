"""Phone warnings: raised once, cleared, and "turn it off?" only creates an approval request."""

import pytest

from backend import actions, agent, alerts, config, db, state
from tests.test_flow import reading


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    agent._analyzing.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def feed(conn, power_w, n=1, kwh=100.0, current=None, ts=1_700_000_000):
    for i in range(n):
        r = reading(power_w)
        r["meter"]["energy_kwh"] = kwh
        r["meter"]["voltage_v"] = 230.0
        if current is not None:
            r["meter"]["current_a"] = current
        r["meter_ts"] = ts + i
        actions.ingest(conn, r)
        alerts.check(conn, "home")


def items(conn):
    return alerts.listing(conn, "home", 50)["items"]


def kinds(conn, active_only=True):
    return [a["kind"] for a in items(conn) if a["active"] or not active_only]


def test_overload_is_danger_raised_once_and_proposes_biggest_device(conn):
    db.set_device(conn, "home", "heater", is_on=1)
    feed(conn, 5300, n=5, current=23.5)                # limit 25 A, danger from 22.5 A
    a = [x for x in items(conn) if x["kind"] == "overload"]
    assert len(a) == 1                                 # one notification, not one per second
    assert a[0]["level"] == alerts.DANGER and a[0]["device_id"] == "heater" and a[0]["can_act"]


def test_current_warning_below_danger_and_clears(conn):
    feed(conn, 4700, current=20.5)
    assert kinds(conn) == ["current_high"]
    feed(conn, 2000, current=8.7)
    assert kinds(conn) == []                           # closed when the current dropped


def test_lab_limit_is_the_10a_meter(conn):
    r = {"site": "lab", "meter": {"power_w": 2100, "current_a": 9.4, "voltage_v": 225}, "rooms": []}
    actions.ingest(conn, r)
    alerts.check(conn, "lab")
    assert [a["kind"] for a in alerts.listing(conn, "lab")["items"]] == ["overload"]


def test_high_power_needs_a_sustained_reading(conn):
    feed(conn, 3500, n=alerts.HIGH_POWER_READINGS - 1, current=5)
    assert "high_power" not in kinds(conn)
    feed(conn, 3500, n=2, current=5)
    assert "high_power" in kinds(conn)


def test_tier_warning_before_crossing_into_the_expensive_tier(conn):
    feed(conn, 500, kwh=230)                           # 77 % of the 300 kWh first tier
    assert "tier_near" not in kinds(conn)
    feed(conn, 500, kwh=250)                           # 83 %: early heads-up
    t = [a for a in items(conn) if a["kind"] == "tier_near"]
    assert len(t) == 1 and t[0]["level"] == alerts.WARN
    assert "50" in t[0]["body"] and "100" in t[0]["body"] and "يوم" in t[0]["body"]
    feed(conn, 500, kwh=255)
    assert len([a for a in items(conn) if a["kind"] == "tier_near"]) == 1   # not again every reading
    feed(conn, 500, kwh=290)                           # 97 %: last call, a second notification
    t = [a for a in items(conn) if a["kind"] == "tier_near" and a["active"]]
    assert len(t) == 1 and t[0]["level"] == alerts.DANGER and "10" in t[0]["body"]
    feed(conn, 500, kwh=310)                           # crossed: the warning closes
    assert "tier_near" not in kinds(conn)


def test_left_on_uses_the_site_clock(conn):
    db.set_device(conn, "home", "heater", is_on=1)
    feed(conn, 2500, ts=1_700_000_000)
    feed(conn, 2500, ts=1_700_000_000 + 3600)
    assert "left_on" not in kinds(conn)
    feed(conn, 2500, ts=1_700_000_000 + 2 * 3600 + 5)
    assert "left_on" in kinds(conn)
    db.set_device(conn, "home", "heater", is_on=0)
    feed(conn, 500, ts=1_700_000_000 + 3 * 3600)
    assert "left_on" not in kinds(conn)


def test_unknown_device_reuses_anomaly_detection(conn):
    feed(conn, 500)
    db.set_state(conn, "anomaly:home", {"open": True, "streak": 0, "kind": "extra", "residual_w": 700, "since": 123.0})
    alerts.check(conn, "home")     # no new reading, so anomaly.observe cannot close it
    a = [x for x in items(conn) if x["kind"] == "unknown_device"][0]
    assert "700" in a["body"] and a["device_id"] is None and not a["can_act"]


def test_cooldown_after_clear(conn):
    alerts.raise_alert(conn, "home", "x", "test", alerts.WARN, "t", "b")
    alerts.resolve(conn, "home", "x")
    assert alerts.raise_alert(conn, "home", "x", "test", alerts.WARN, "t", "b") is None
    assert alerts.raise_alert(conn, "home", "x", "test", alerts.WARN, "t", "b",
                              now=10**10) is not None


def test_act_creates_approval_and_switches_nothing(conn):
    db.set_device(conn, "home", "heater", is_on=1)
    feed(conn, 5300, current=23.5)
    a = items(conn)[0]
    out = alerts.act(conn, "home", a["id"])
    p = actions.pending_approval(conn, "home")
    assert p and p["id"] == out["approval_id"] and p["device_id"] == "heater" and not p["turn_on"]
    assert db.device(conn, "home", "heater")["is_on"] == 1   # still on: the human must approve first
    assert items(conn)[0]["user_state"] == "acted" and not items(conn)[0]["can_act"]
    with pytest.raises(actions.ActionError):               # one question at a time
        alerts.act(conn, "home", a["id"])
    actions.reject(conn, "home", p["id"])
    assert db.device(conn, "home", "heater")["is_on"] == 1   # reject means no action


def test_act_refuses_critical_and_sensitive(conn):
    for dev in ("fridge", "router"):
        aid = alerts.raise_alert(conn, "home", f"k:{dev}", "test", alerts.WARN, "t", "b", device_id=dev)
        with pytest.raises(actions.ActionError):
            alerts.act(conn, "home", aid)
    assert actions.pending_approval(conn, "home") is None


def test_dismiss_and_state(conn):
    feed(conn, 4700, current=20.5)
    a = items(conn)[0]
    alerts.dismiss(conn, "home", a["id"])
    feed(conn, 4700, current=20.5)
    assert len(items(conn)) == 1                        # dismissed, still active: not raised again
    s = state.build(conn, "home")
    assert s["alerts"]["last_id"] == a["id"] and s["alerts"]["open"] == 0


def test_agent_tick_raises_alerts(conn):
    import time
    r = reading(5300)
    r["meter"]["current_a"] = 23.5
    actions.ingest(conn, r)
    agent.tick(conn, "home", time.time())
    assert "overload" in kinds(conn)
