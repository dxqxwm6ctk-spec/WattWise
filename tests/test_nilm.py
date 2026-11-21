"""Teach mode and NILM-lite: steps on the meter, guesses, the conversation, unknown devices."""

import pytest

from backend import actions, config, db, llm, nilm, teach


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(teach, "QUIET_S", 10_000)     # the tests call teach.finish() themselves
    nilm.reset_buffers()
    db.init_db()
    with db.connect() as c:
        yield c
    nilm.reset_buffers()


# ---------- pure helpers ----------

def buf(values, pf=None):
    return [(i, v, nilm.reactive(v, pf)) for i, v in enumerate(values)]


def test_clean_step_is_found_with_its_power_factor():
    # 20 W base at pf 1.0, then a 60 W device at pf 0.6 joins: total 80 W.
    q_dev = 60 * (0.8 / 0.6)
    b = [(i, 20.0, 0.0) for i in range(3)] + [(i, 80.0, q_dev) for i in range(3, 6)]
    ev = nilm.detect_step(b, precise=True)
    assert ev and round(ev["dp"]) == 60 and ev["pf"] == 0.6 and ev["pf_quality"] == "ok"


def test_ramp_and_small_wobble_are_not_steps():
    assert nilm.detect_step(buf([100, 110, 120, 130, 140, 150]), precise=True) is None
    assert nilm.detect_step(buf([100, 100.5, 99.8, 101, 100.2, 100.4]), precise=True) is None


def test_noisy_main_meter_needs_a_big_step():
    assert nilm.detect_step(buf([2000, 2015, 1990, 2020, 2005, 2010]), precise=False) is None
    ev = nilm.detect_step(buf([2000, 2015, 1990, 2070, 2060, 2075]), precise=False)
    assert ev and ev["dp"] > 40 and ev["noisy"]


def test_power_factor_tells_laptop_from_fan_and_lamp():
    assert nilm.guess(61, 0.58)[0]["kind"] == "pc"
    assert nilm.guess(55, 0.87)[0]["kind"] == "fan"
    assert nilm.guess(40, 0.99)[0]["label"].startswith("لمبة عادية")
    assert nilm.guess(1800, 1.0)[0]["kind"] == "heater"


def test_fingerprint_matching():
    assert nilm.matches(60, 0.6, 62, 0.58)
    assert not nilm.matches(60, 0.6, 62, 0.9)          # same watts, different pf
    assert not nilm.matches(60, None, 90, None)
    assert nilm.matches(80, 0.9, 60, 0.6, noisy=True)  # main meter: wide watts, pf ignored


@pytest.mark.parametrize("text,expected", [
    ("الأول لابتوب، الثاني ضو المكتب", {1: {"name": "لابتوب"}, 2: {"name": "ضو المكتب"}}),
    ("الاول لابتوب والثاني ضو صغير و3 تجاهله", {1: {"name": "لابتوب"}, 2: {"name": "ضو صغير"}, 3: {"drop": True}}),
    ("الثالث مش لمبة عادية، ضو السقف", {3: {"name": "ضو السقف"}}),
    ("الـ40 واط هو ضو السقف", {3: {"name": "ضو السقف"}}),
    ("١ لابتوب، ٢ شاحن", {1: {"name": "لابتوب"}, 2: {"name": "شاحن"}}),
])
def test_parse_labels(text, expected):
    cands = [{"w": 61}, {"w": 8}, {"w": 40}]
    assert teach.parse_labels(text, cands) == expected


def test_yes_no_and_kinds():
    assert teach.is_yes("صح") and teach.is_yes("آه احفظهم") and not teach.is_yes("لا")
    assert teach.is_no("لأ ما بدي") and teach.is_no("لا تحفظ")
    assert teach.kind_from_name("ضو المكتب") == "light"
    assert teach.kind_from_name("الثلاجة الصغيرة") == "fridge"


# ---------- live flow on the real-lab site (one room, precise PZEM) ----------

def lab(conn, watts, pf=None, n=3):
    for _ in range(n):
        actions.ingest(conn, {"site": "lab", "source": "device",
                              "meter": {"power_w": watts, "energy_kwh": 1.0, "pf": pf},
                              "rooms": [{"room_id": "lab", "temp_c": 25, "occupied": True}]})


def chat(conn, site="lab"):
    return [m["text"] for m in teach.messages(conn, site)]


def test_teach_flow_saves_only_after_yes(conn):
    teach.start(conn, "lab", "lab")
    lab(conn, 85, 0.95)                  # lamp + fan already there
    lab(conn, 146, 0.83)                 # + laptop (about 61 W, low pf)
    lab(conn, 154, 0.84)                 # + small LED (8 W)
    assert len(teach.session(conn, "lab")["candidates"]) == 2
    teach.finish(conn, "lab")
    assert "هل هذا صحيح" in chat(conn)[-1]
    teach.say(conn, "lab", "الأول لابتوب، الثاني ضو المكتب")
    assert "هل أحفظ" in chat(conn)[-1]
    assert nilm.fingerprints(conn, "lab") == []          # nothing saved before the yes
    teach.say(conn, "lab", "احفظ")
    names = {f["name"]: f for f in nilm.fingerprints(conn, "lab")}
    assert set(names) == {"لابتوب", "ضو المكتب"}
    assert names["لابتوب"]["kind"] == "pc" and 55 <= names["لابتوب"]["watts"] <= 66
    assert teach.session(conn, "lab") is None


def test_teach_flow_no_means_nothing_saved(conn):
    teach.start(conn, "lab", "lab")
    lab(conn, 85, 0.95)
    lab(conn, 146, 0.83)
    teach.finish(conn, "lab")
    teach.say(conn, "lab", "صح")
    teach.say(conn, "lab", "لا")
    assert nilm.fingerprints(conn, "lab") == []
    assert teach.session(conn, "lab") is None


def test_unknown_device_alert_then_label_then_recognised(conn):
    lab(conn, 85, 0.95)
    lab(conn, 145, 0.85)                 # a 60 W device nobody taught us
    st = nilm.status(conn, "lab")
    assert len(st["unknown"]) == 1 and st["unknown"][0]["room"] == "lab"
    assert "جهاز مجهول" in chat(conn)[-1]
    teach.say(conn, "lab", "هاد مكوى")
    teach.say(conn, "lab", "اه")
    fp = nilm.fingerprints(conn, "lab")
    assert len(fp) == 1 and fp[0]["name"] == "مكوى" and fp[0]["room"] == "lab"
    # It switches off and on again: recognised, no new unknown alert.
    lab(conn, 85, 0.95)
    lab(conn, 145, 0.85)
    assert nilm.status(conn, "lab")["unknown"] == []
    log = [r["event"] for r in db.rows(conn.execute("SELECT event FROM audit_log WHERE site='lab'"))]
    assert "recognised_off" in log and "recognised" in log


def test_ignore_unknown_saves_nothing(conn):
    lab(conn, 85, 0.95)
    lab(conn, 145, 0.85)
    teach.say(conn, "lab", "تجاهل")
    assert nilm.fingerprints(conn, "lab") == []
    assert nilm.status(conn, "lab")["unknown"] == []


def test_relay_switch_by_the_agent_is_not_an_unknown_device(conn):
    lab(conn, 85, 0.95)
    db.set_device(conn, "lab", "fan", is_on=0)
    lab(conn, 40, 1.0)                    # the fan's step down
    db.set_device(conn, "lab", "fan", is_on=1)
    lab(conn, 85, 0.95)                   # and back up
    assert nilm.status(conn, "lab")["unknown"] == []


def test_simulator_room_circuit_is_used_in_teach_mode(conn):
    teach.start(conn, "home", "kids")
    assert actions.commands_for(conn, "home")["room_meter"]["room"] == "kids"

    def home(circuit_w, pf):
        for _ in range(3):
            actions.ingest(conn, {"site": "home", "source": "simulator",
                                  "meter": {"power_w": 2000, "energy_kwh": 1.0},
                                  "circuit": {"room_id": "kids", "power_w": circuit_w, "pf": pf},
                                  "rooms": []})
    home(65, 0.75)
    home(73, 0.74)                        # an 8 W LED: only visible on the room's breaker
    c = teach.session(conn, "home")["candidates"]
    assert len(c) == 1 and round(c[0]["w"]) == 8
    teach.cancel(conn, "home")
    rm = actions.commands_for(conn, "home")["room_meter"]
    assert rm["room"] == "kids" and not rm["guided"]   # the PZEM stays on that breaker
    actions.reset_demo(conn, "home")
    assert actions.commands_for(conn, "home")["room_meter"] is None


class FakeProvider(llm.Provider):
    name, model = "fake", "fake-model"

    def run(self, system, user, tools, call_tool, final_tools):
        return llm.RunResult(final_tool="submit_reading", input_tokens=10, output_tokens=10, final_input={
            "intent": "labels", "room_id": "",
            "items": [{"n": 1, "name": "لابتوب الشغل", "ignore": False}]})


def test_llm_reads_the_reply_when_available(conn):
    llm.set_provider(FakeProvider())
    teach.start(conn, "lab", "lab")
    lab(conn, 85, 0.95)
    lab(conn, 146, 0.83)
    teach.finish(conn, "lab")
    teach.say(conn, "lab", "هاد تبع الشغل")       # the rules would not get this; the LLM does
    assert "لابتوب الشغل" in chat(conn)[-1]
    teach.say(conn, "lab", "احفظ")               # saving still needs the user's yes
    assert nilm.fingerprints(conn, "lab")[0]["name"] == "لابتوب الشغل"


def test_fridge_cycling_is_known_and_a_device_hidden_in_a_fridge_step_is_found(conn):
    teach.start(conn, "home", "kitchen")
    teach.cancel(conn, "home")            # the PZEM stays on the kitchen breaker

    def kitchen(w):
        for _ in range(3):
            actions.ingest(conn, {"site": "home", "source": "simulator", "meter": {"power_w": 2000, "energy_kwh": 1.0},
                                  "circuit": {"room_id": "kitchen", "power_w": w, "pf": 0.75}, "rooms": []})
    kitchen(12)
    kitchen(152)                          # the fridge (140 W) starts: known, no alert
    kitchen(12)                           # and stops
    assert nilm.status(conn, "home")["unknown"] == []
    kitchen(212)                          # fridge + a 60 W stranger in the same second
    u = nilm.status(conn, "home")["unknown"]
    assert len(u) == 1 and u[0]["watts"] == 60 and u[0]["room"] == "kitchen"
    assert "في المطبخ" in chat(conn, "home")[-1]


def test_noisy_main_meter_reports_only_big_unknown_devices(conn):
    def home(w):
        for _ in range(3):
            actions.ingest(conn, {"site": "home", "source": "simulator", "meter": {"power_w": w, "energy_kwh": 1.0},
                                  "rooms": []})
    home(2000)
    home(2060)                            # 60 W: could be anything on a noisy whole-house meter
    assert nilm.status(conn, "home")["unknown"] == []
    home(2760)                            # 700 W: reported (room unknown)
    u = nilm.status(conn, "home")["unknown"]
    assert len(u) == 1 and u[0]["room"] is None


def test_unknown_device_during_teach_is_asked_about_afterwards(conn):
    teach.start(conn, "lab", "lab")
    lab(conn, 85, 0.95)
    lab(conn, 146, 0.83)
    teach.finish(conn, "lab")             # now waiting for "صح"
    lab(conn, 206, 0.86)                  # another 60 W device shows up meanwhile
    assert "سنعود إليه" in chat(conn)[-1]
    teach.say(conn, "lab", "صح")
    teach.say(conn, "lab", "لا")          # nothing saved, teach mode ends ...
    assert "ما هذا الجهاز" in chat(conn)[-1]   # ... and the AI asks about the unknown device
