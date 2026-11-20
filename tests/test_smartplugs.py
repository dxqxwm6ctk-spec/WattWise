"""WiFi smart plugs: Policy Guard rules, safety warnings, the sync loop and the brand drivers."""

import sys
import types

import pytest

from backend import actions, agent, config, db, policy, smartplugs
from backend.plugs import PlugError, scan, shelly, simulated, tasmota, tuya
from tests.test_flow import reading

LIGHT = {"id": "x", "name": "لمبة", "kind": "light", "tier": "T1", "allow": 1, "signature_w": 30}
HEATER = {"id": "h", "name": "سخّان", "kind": "heater", "tier": "T1", "allow": 1, "signature_w": 2600}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "VERIFY_AFTER_S", 0)
    agent._analyzing.clear()
    simulated._STATE.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def add_sim(conn, kind="tv", host="sim-shelly-1", room="bedroom", **kw):
    d = smartplugs.add(conn, "home", "simulated", host, {}, kw.pop("name", "تلفزيون النوم"), room, kind,
                       kw.pop("allow", True), **kw)
    conn.commit()   # the sync loop uses its own connection
    return d


# ---------- Policy Guard ----------

def test_offline_plug_blocks_everyone():
    d = policy.check_switch(LIGHT, False, policy.HUMAN, None, plug={"online": 0, "max_w": 2300})
    assert not d.allowed and d.code == "plug_offline"


def test_plug_never_switches_on_a_load_above_its_rating():
    d = policy.check_switch(HEATER, True, policy.HUMAN, None, plug={"online": 1, "max_w": 2300})
    assert not d.allowed and d.code == "plug_overload"
    # switching it OFF is always fine
    assert policy.check_switch(HEATER, False, policy.HUMAN, None, plug={"online": 1, "max_w": 2300}).allowed


def test_critical_load_on_a_plug_is_still_forbidden():
    fridge = {**LIGHT, "kind": "fridge", "tier": "T2"}
    assert policy.check_switch(fridge, False, policy.HUMAN, None, plug={"online": 1, "max_w": 2300}).code == "critical_load"


# ---------- safety warnings ----------

def test_safety_levels():
    assert smartplugs.safety("light", 30, 2300)["level"] == "ok"
    heater = smartplugs.safety("heater", 2000, 3680)
    assert heater["level"] == "heater" and heater["needs_confirm"] and "كونتاكتور" in heater["message"]
    assert smartplugs.safety("other", 1900, 2300)["level"] == "warn"
    assert smartplugs.safety("other", 2500, 2300)["level"] == "block"


def test_heater_needs_confirmation(conn):
    with pytest.raises(actions.ActionError, match="confirm_high_power"):
        smartplugs.add(conn, "home", "simulated", "sim-tapo-1", {"max_a": 16}, "سخّان", "bath", "heater", True)
    assert db.plug(conn, "home", "x") is None
    d = smartplugs.add(conn, "home", "simulated", "sim-tapo-1", {"max_a": 16}, "سخّان", "bath", "heater", True,
                       confirm_high_power=True)
    assert db.plug(conn, "home", d["id"])["max_w"] == 16 * 230


def test_same_plug_cannot_be_added_twice(conn):
    add_sim(conn)
    with pytest.raises(actions.ActionError):
        add_sim(conn, kind="light")


# ---------- add, sync, control ----------

def test_add_simulated_plug_measures_the_signature(conn):
    d = add_sim(conn, kind="tv")
    assert d["added"] == 1 and d["signature_measured"] == 1
    assert 90 < d["signature_w"] < 130            # typical TV, measured by the plug
    assert actions.commands_for(conn, "home")["plug_loads"][d["id"]] > 0   # simulator adds it to the meter


def test_sync_pushes_human_toggle_to_the_plug(conn):
    d = add_sim(conn)
    actions.human_toggle(conn, "home", d["id"], False)
    conn.commit()
    smartplugs.sync_all()
    assert simulated._STATE["sim-shelly-1"]["on"] is False
    p = db.plug(conn, "home", d["id"])
    assert p["reported_on"] == 0 and p["power_w"] == 0


def test_plug_button_is_a_manual_change(conn):
    d = add_sim(conn)
    smartplugs.sync_all()
    simulated.switch("sim-shelly-1", {}, False)    # someone pressed the plug's own button
    smartplugs.sync_all()
    assert db.device(conn, "home", d["id"])["is_on"] == 0
    assert db.one(conn.execute("SELECT 1 AS x FROM audit_log WHERE event='plug_button'"))


def test_offline_plug_after_three_failed_polls(conn, monkeypatch):
    d = add_sim(conn)

    def broken(host, options):
        raise PlugError("ما رد")
    monkeypatch.setattr(simulated, "status", broken)
    for _ in range(3):
        smartplugs.sync_all()
    assert db.plug(conn, "home", d["id"])["online"] == 0
    with pytest.raises(actions.ActionError):
        actions.human_toggle(conn, "home", d["id"], False)


def test_agent_action_is_verified_on_the_plug(conn):
    d = add_sim(conn, kind="tv")
    actions.ingest(conn, reading(2500, bedroom_occupied=False))
    aid = actions.request_approval(conn, "home", d, False, "نطفي التلفزيون؟", "ما حدا بالغرفة", {})
    actions.approve(conn, "home", aid)
    conn.commit()
    smartplugs.sync_all()        # pushes OFF and reads ~0 W back
    agent._verify(conn, "home", __import__("time").time() + 1)
    assert db.device(conn, "home", d["id"])["agent_off"] == actions.AGENT_OFF_VERIFIED
    assert db.one(conn.execute("SELECT 1 AS x FROM audit_log WHERE event='verified'"))


def test_remove_plug(conn):
    d = add_sim(conn)
    smartplugs.remove(conn, "home", d["id"])
    assert db.device(conn, "home", d["id"]) is None and "sim-shelly-1" not in simulated._STATE


def test_public_view_hides_the_local_key(conn):
    row = {"brand": "tuya", "model": None, "host": "1.2.3.4", "online": 1, "meters": 1, "power_w": 5.0,
           "voltage_v": 230, "max_w": 2300, "error": None, "options": '{"local_key": "secret"}'}
    assert "secret" not in str(smartplugs.public(row))


def test_scan_without_lan_lists_simulated_plugs():
    found = scan.scan(include_lan=False)
    assert {f["brand"] for f in found} == {"simulated"} and len(found) == 4


# ---------- brand drivers (fake network answers) ----------

def test_shelly_gen2_status(monkeypatch):
    def fake(method, url, body=None, timeout=2, auth=None):
        assert "Switch.GetStatus" in url
        return {"output": True, "apower": 41.5, "voltage": 229.8, "aenergy": {"total": 1200}}
    monkeypatch.setattr(shelly, "http_json", fake)
    s = shelly.status("10.0.0.5", {"gen": 2})
    assert s.on and s.power_w == 41.5 and s.energy_kwh == 1.2


def test_shelly_gen1_switch(monkeypatch):
    calls = []
    monkeypatch.setattr(shelly, "http_json", lambda m, url, *a, **k: calls.append(url) or {})
    shelly.switch("10.0.0.5", {"gen": 1}, False)
    assert calls == ["http://10.0.0.5/relay/0?turn=off"]


def test_tasmota_status(monkeypatch):
    def fake(method, url, body=None, timeout=2, auth=None):
        if "Status" in url:
            return {"StatusSNS": {"ENERGY": {"Power": 12, "Voltage": 231, "Total": 3.4}}}
        return {"POWER": "ON"}
    monkeypatch.setattr(tasmota, "http_json", fake)
    s = tasmota.status("10.0.0.6", {})
    assert s.on and s.power_w == 12 and s.energy_kwh == 3.4


def test_tuya_status_uses_deciwatts(monkeypatch):
    class Fake:
        def __init__(self, *a, **k): pass
        def set_socketTimeout(self, t): pass
        def set_socketRetryLimit(self, n): pass
        def status(self): return {"dps": {"1": True, "19": 455, "20": 2301}}
    monkeypatch.setitem(sys.modules, "tinytuya", types.SimpleNamespace(OutletDevice=Fake))
    s = tuya.status("10.0.0.7", {"device_id": "abc", "local_key": "k"})
    assert s.on and s.power_w == 45.5 and s.voltage_v == 230.1


def test_tuya_needs_a_local_key(monkeypatch):
    monkeypatch.setitem(sys.modules, "tinytuya", types.SimpleNamespace(OutletDevice=object))
    with pytest.raises(PlugError, match="Local Key"):
        tuya.status("10.0.0.7", {"device_id": "abc"})
