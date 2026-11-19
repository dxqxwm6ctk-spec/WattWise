"""Everything that changes the system's state.

Both the web API (human actions) and the agent loop call these functions, so
every change goes through the same Policy Guard checks and the same audit log.
"""

import json
import time

from backend import config, db, policy

# Approval statuses
PENDING, APPROVED, REJECTED, EXPIRED, BLOCKED, CANCELLED = (
    "pending", "approved", "rejected", "expired", "blocked", "cancelled")

# devices.agent_off values
AGENT_OFF_NONE, AGENT_OFF_UNVERIFIED, AGENT_OFF_VERIFIED = 0, 1, 2

GOAL_STEPS = [
    "قراءة العدّاد والحسّاسات والطقس",
    "تعلّم بصمة كل جهاز",
    "كشف الهدر بكل غرفة",
    "التخطيط واقتراح إجراء",
    "انتظار موافقة صاحب البيت",
    "التنفيذ عبر المقبس الذكي",
    "التحقق بالعدّاد وتحديث الفاتورة",
]


class ActionError(Exception):
    """A request that cannot be done. The message is Arabic, safe to show."""


# ---------- small state helpers ----------

def flag(conn, name: str, site: str) -> bool:
    return bool(db.get_state(conn, f"{name}:{site}", False))


def set_phase(conn, site: str, phase: str) -> None:
    db.set_state(conn, f"phase:{site}", phase)


def get_phase(conn, site: str) -> str:
    return db.get_state(conn, f"phase:{site}", "normal")


def active_goal(conn, site: str) -> dict | None:
    return db.one(conn.execute(
        "SELECT * FROM goals WHERE site=? AND active=1 ORDER BY id DESC LIMIT 1", (site,)))


def pending_approval(conn, site: str) -> dict | None:
    return db.one(conn.execute(
        "SELECT * FROM approvals WHERE site=? AND status=? ORDER BY id DESC LIMIT 1", (site, PENDING)))


def require_site(site: str) -> None:
    if site not in config.load_sites():
        raise ActionError("هذا الموقع مش معروف.")


def require_device(conn, site: str, device_id: str) -> dict:
    d = db.device(conn, site, device_id)
    if not d:
        raise ActionError("هذا الجهاز مش موجود.")
    return d


# ---------- readings from the ESP32 or the simulator ----------

def ingest(conn, payload: dict) -> None:
    """Store one reading: the main meter plus each room's sensors."""
    site = payload["site"]
    require_site(site)
    now = time.time()
    meter = payload["meter"]
    meter_ts = float(payload.get("meter_ts") or now)

    prev = db.latest_meter(conn, site)
    # Time step on the site's clock (the simulator runs faster than real time).
    dt_h = 0.0
    if prev and meter_ts > prev["meter_ts"]:
        dt_h = min(meter_ts - prev["meter_ts"], 600) / 3600

    devs = db.devices(conn, site)
    held_off_w = 0.0
    for d in devs:
        # NILM-lite attribution: a device that is on draws its learned signature.
        if d["is_on"] and dt_h:
            conn.execute("UPDATE devices SET energy_wh = energy_wh + ? WHERE site=? AND id=?",
                         (d["signature_w"] * dt_h, site, d["id"]))
        if d["agent_off"] == AGENT_OFF_VERIFIED:
            held_off_w += d["signature_w"]

    # Measured savings: only for actions the meter has already confirmed.
    if held_off_w and dt_h:
        saved = db.get_state(conn, f"saved_wh:{site}", 0.0) + held_off_w * dt_h
        db.set_state(conn, f"saved_wh:{site}", saved)

    power = float(meter["power_w"])
    conn.execute(
        "INSERT INTO meter_readings (site, ts, meter_ts, source, power_w, baseline_w, energy_kwh, "
        "voltage_v, current_a, freq_hz) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (site, now, meter_ts, payload.get("source", "device"), power, power + held_off_w,
         meter.get("energy_kwh"), meter.get("voltage_v"), meter.get("current_a"), meter.get("freq_hz")),
    )
    for r in payload.get("rooms", []):
        conn.execute(
            "INSERT INTO room_readings (site, room_id, ts, temp_c, humidity, light, occupied, window_open) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (site, r["room_id"], now, r.get("temp_c"), r.get("humidity"), r.get("light"),
             None if r.get("occupied") is None else int(r["occupied"]),
             None if r.get("window_open") is None else int(r["window_open"])),
        )

    # The physical emergency-stop button on the ESP32.
    if payload.get("estop_pressed") and not flag(conn, "estop", site):
        emergency_stop(conn, site, by="device")


def commands_for(conn, site: str) -> dict:
    """What the ESP32 / simulator should do now. Polled every second."""
    require_site(site)
    devs = db.devices(conn, site)
    return {
        "relays": {d["id"]: bool(d["is_on"]) for d in devs},
        "setpoints": {d["id"]: d["setpoint"] for d in devs if d["setpoint"] is not None},
        "approval_pending": pending_approval(conn, site) is not None,  # buzzer + yellow LED
        "estop": flag(conn, "estop", site),
        "safe_mode": flag(conn, "safe_mode", site),
        "scenario": db.get_state(conn, f"scenario:{site}", "normal"),
        # While the user adds a device in the app (simulator plugs in a matching load).
        "learning": _learning(conn, site),
    }


def _learning(conn, site: str) -> dict | None:
    s = db.get_state(conn, f"learn:{site}")
    if not s:
        return None
    return {"device_id": s["device_id"], "kind": s["kind"]}


# ---------- goal ----------

def set_goal(conn, site: str, text: str, bill_target_jd: float | None) -> dict:
    require_site(site)
    text = text.strip()
    if not text:
        raise ActionError("اكتب الهدف.")
    conn.execute("UPDATE goals SET active=0 WHERE site=?", (site,))
    conn.execute("INSERT INTO goals (site, created_ts, text, bill_target_jd, active) VALUES (?,?,?,?,1)",
                 (site, time.time(), text, bill_target_jd))
    db.audit(conn, site, "T0", "agent", "goal_received",
             f"استلمت الهدف وقسّمته لـ{len(GOAL_STEPS)} خطوات. الوضع: مراقبة.",
             {"goal": text, "steps": GOAL_STEPS})
    if get_phase(conn, site) not in ("stopped",):
        set_phase(conn, site, "normal")
    return active_goal(conn, site)


# ---------- human controls ----------

def human_toggle(conn, site: str, device_id: str, turn_on: bool, confirmed: bool = False) -> dict:
    d = require_device(conn, site, device_id)
    decision = policy.check_switch(d, turn_on, policy.HUMAN, None)
    if not decision.allowed:
        db.audit(conn, site, "T2", "policy", "blocked",
                 f"محاولة تحكم بـ{d['name']} ← مرفوضة بالكود. {decision.reason_ar}")
        raise ActionError(decision.reason_ar)

    if d["sensitive"] and not turn_on and not confirmed:
        raise ActionError("confirm_required")

    db.set_device(conn, site, device_id, is_on=int(turn_on), agent_off=AGENT_OFF_NONE)
    if d["sensitive"]:
        if not turn_on:
            db.set_state(conn, f"safe_mode:{site}", True)
            _close_pending(conn, site, EXPIRED)
            db.audit(conn, site, "MANUAL", "human", "manual_switch",
                     f"إطفاء {d['name']} من المستخدم. الوكيل دخل الوضع الآمن: بدون موافقة ما في إجراء، والأجهزة بتضل متل ما هي.")
            set_phase(conn, site, "offline")
        else:
            db.set_state(conn, f"safe_mode:{site}", False)
            db.audit(conn, site, "MANUAL", "human", "manual_switch",
                     f"تشغيل {d['name']} من المستخدم. رجع الاتصال وتطبيق الموافقة.")
            if get_phase(conn, site) == "offline":
                set_phase(conn, site, "normal")
    else:
        db.audit(conn, site, "MANUAL", "human", "manual_switch",
                 f"{'تشغيل' if turn_on else 'إطفاء'} {d['name']} من المستخدم.")
    return db.device(conn, site, device_id)


def set_setpoint(conn, site: str, device_id: str, value: float) -> dict:
    d = require_device(conn, site, device_id)
    decision = policy.check_setpoint(d, value)
    if not decision.allowed:
        db.audit(conn, site, "T0", "policy", "blocked", f"حارس السياسات: {decision.reason_ar}")
        raise ActionError(decision.reason_ar)
    db.set_device(conn, site, device_id, setpoint=value)
    return db.device(conn, site, device_id)


# ---------- approvals ----------

def request_approval(conn, site: str, device: dict, turn_on: bool, title: str, reason: str,
                     details: dict) -> int:
    now = time.time()
    cur = conn.execute(
        "INSERT INTO approvals (site, device_id, turn_on, created_ts, expires_ts, title, reason, details, status) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (site, device["id"], int(turn_on), now, now + config.APPROVAL_TIMEOUT_S, title, reason,
         json.dumps(details, ensure_ascii=False), PENDING),
    )
    set_phase(conn, site, "pending")
    return cur.lastrowid


def _get_pending(conn, site: str, approval_id: int) -> dict:
    a = db.one(conn.execute("SELECT * FROM approvals WHERE id=? AND site=?", (approval_id, site)))
    if not a:
        raise ActionError("طلب الموافقة مش موجود.")
    if a["status"] != PENDING:
        raise ActionError("هذا الطلب انتهى.")
    if policy.approval_expired(a["created_ts"], time.time()):
        expire_approval(conn, a)
        raise ActionError("انتهت المهلة، فما عملنا إشي.")
    return a


def approve(conn, site: str, approval_id: int) -> dict:
    a = _get_pending(conn, site, approval_id)
    d = require_device(conn, site, a["device_id"])
    room = db.latest_room(conn, site, d["room"])
    # The Policy Guard checks again at execution time: things may have changed.
    decision = policy.check_switch(d, bool(a["turn_on"]), policy.AGENT, room,
                                   estop=flag(conn, "estop", site), safe_mode=flag(conn, "safe_mode", site))
    now = time.time()
    if not decision.allowed:
        conn.execute("UPDATE approvals SET status=?, decided_ts=? WHERE id=?", (BLOCKED, now, a["id"]))
        db.audit(conn, site, "T2", "policy", "blocked",
                 f"وافقتي، بس حارس السياسات رفض التنفيذ: {decision.reason_ar}")
        set_phase(conn, site, "rejected")
        raise ActionError(decision.reason_ar)

    before = db.avg_power(conn, site, 3) or 0.0
    conn.execute("UPDATE approvals SET status=?, decided_ts=?, power_before=? WHERE id=?",
                 (APPROVED, now, before, a["id"]))
    db.audit(conn, site, "OK", "human", "approved",
             "موافقة من تطبيق الهاتف. حارس السياسات: الجهاز ضمن القائمة المسموحة ✓")
    db.set_device(conn, site, d["id"], is_on=int(a["turn_on"]),
                  agent_off=AGENT_OFF_NONE if a["turn_on"] else AGENT_OFF_UNVERIFIED)
    db.audit(conn, site, "T1", "agent", "command",
             f"أمر للمقبس الذكي: {'تشغيل' if a['turn_on'] else 'إطفاء'} {d['name']}.")
    set_phase(conn, site, "executing")
    return db.one(conn.execute("SELECT * FROM approvals WHERE id=?", (a["id"],)))


def reject(conn, site: str, approval_id: int) -> dict:
    a = _get_pending(conn, site, approval_id)
    d = db.device(conn, site, a["device_id"])
    conn.execute("UPDATE approvals SET status=?, decided_ts=? WHERE id=?", (REJECTED, time.time(), a["id"]))
    db.audit(conn, site, "T1", "human", "rejected",
             f"رفضتي ← لا إجراء. {d['name'] if d else 'الجهاز'} بقي متل ما هو.")
    set_phase(conn, site, "rejected")
    return db.one(conn.execute("SELECT * FROM approvals WHERE id=?", (a["id"],)))


def expire_approval(conn, a: dict) -> None:
    conn.execute("UPDATE approvals SET status=?, decided_ts=? WHERE id=?", (EXPIRED, time.time(), a["id"]))
    db.audit(conn, a["site"], "T1", "policy", "expired", "انتهت المهلة بدون رد ← لا إجراء. السكوت مش موافقة.")
    set_phase(conn, a["site"], "expired")


def _close_pending(conn, site: str, status: str) -> None:
    conn.execute("UPDATE approvals SET status=?, decided_ts=? WHERE site=? AND status=?",
                 (status, time.time(), site, PENDING))


# ---------- emergency stop, fail-safe, reset ----------

def restore_normal(conn, site: str) -> None:
    """Return every device to its normal state and drop the agent's holds."""
    conn.execute("UPDATE devices SET is_on=normal_on, agent_off=? WHERE site=?", (AGENT_OFF_NONE, site))


def emergency_stop(conn, site: str, by: str = "ui") -> None:
    db.set_state(conn, f"estop:{site}", True)
    _close_pending(conn, site, CANCELLED)
    restore_normal(conn, site)
    db.set_state(conn, f"safe_mode:{site}", False)
    where = "من الزر على الجهاز" if by == "device" else "من الشاشة"
    db.audit(conn, site, "STOP", "human", "estop",
             f"إيقاف طوارئ ({where}): الوكيل معطّل والأجهزة رجعت لوضعها الطبيعي.")
    set_phase(conn, site, "stopped")


def reset_demo(conn, site: str) -> None:
    """Clear the emergency stop and the demo scenario, back to a normal house."""
    db.set_state(conn, f"estop:{site}", False)
    db.set_state(conn, f"safe_mode:{site}", False)
    db.set_state(conn, f"scenario:{site}", "normal")
    db.set_state(conn, f"saved_wh:{site}", 0.0)
    db.set_state(conn, f"learn:{site}", None)
    _close_pending(conn, site, CANCELLED)
    restore_normal(conn, site)
    for d in config.load_sites()[site]["devices"]:
        if d.get("setpoint") is not None:
            db.set_device(conn, site, d["id"], setpoint=d["setpoint"])
    db.audit(conn, site, "T0", "human", "reset", "إعادة ضبط العرض.")
    set_phase(conn, site, "normal")


# ---------- simulator demo controls ----------

def set_scenario(conn, site: str, name: str) -> None:
    """Simulator only: create a waste situation to demo the agent."""
    if config.load_sites()[site]["source"] != "simulator":
        raise ActionError("السيناريوهات للمحاكي بس.")
    if flag(conn, "estop", site):
        raise ActionError("الوكيل موقوف (طوارئ). اعمل إعادة ضبط أول.")
    if name not in SCENARIOS:
        raise ActionError("سيناريو مش معروف.")
    db.set_state(conn, f"scenario:{site}", name)
    if name == "bedroom_empty_window":
        db.set_device(conn, site, "bedAc", is_on=1, agent_off=AGENT_OFF_NONE)
    if get_phase(conn, site) not in ("pending", "executing"):
        set_phase(conn, site, "normal")
    db.audit(conn, site, "T0", "system", "scenario", "محاكاة: " + SCENARIOS[name])


SCENARIOS = {
    "normal": "رجع البيت طبيعي.",
    "bedroom_empty_window": "غرفة النوم الإشغال فاضي، وحسّاس الشباك (محاكى) مفتوح. المكيّف شغّال.",
    "heat_wave": "موجة حر: حرارة الغرف أعلى بـ5 درجات.",
    "holiday": "عطلة: البيت كله فاضي والأجهزة ضلّت شغّالة.",
    "sensor_fault": "عطل حسّاسات: المحاكي بيوقف يبعت قراءات شوي.",
}


# ---------- adding a new device (load signature learning) ----------

KIND_TIERS = {"fridge": "T2", "medical": "T2", "fire_alarm": "T2", "emergency_light": "T2"}


def start_learning(conn, site: str, kind: str) -> dict:
    require_site(site)
    session = {
        "device_id": f"d{int(time.time() * 1000)}",
        "kind": kind,
        "status": "measuring",
        "started_ts": time.time(),
        "before_w": db.avg_power(conn, site, 3) or 0.0,
        "learned_w": None,
    }
    db.set_state(conn, f"learn:{site}", session)
    return session


def finish_learning_if_ready(conn, site: str) -> None:
    """Called by the agent loop: measure the step in watts after the user switched the device on."""
    s = db.get_state(conn, f"learn:{site}")
    if not s or s["status"] != "measuring" or time.time() - s["started_ts"] < 3:
        return
    after = db.avg_power(conn, site, 1.5) or 0.0
    s["learned_w"] = round(max(0.0, after - s["before_w"]))
    s["status"] = "done"
    db.set_state(conn, f"learn:{site}", s)


def add_device(conn, site: str, room: str, name: str, kind: str, allow: bool) -> dict:
    s = db.get_state(conn, f"learn:{site}")
    if not s or s["status"] != "done" or s["kind"] != kind:
        raise ActionError("لازم نقيس بصمة الجهاز أول.")
    if not db.one(conn.execute("SELECT 1 AS x FROM rooms WHERE site=? AND id=?", (site, room))):
        raise ActionError("الغرفة مش معروفة.")
    tier = KIND_TIERS.get(kind, "T1")
    sensitive = kind == "router"
    allow = bool(allow) and tier == "T1" and not sensitive
    conn.execute(
        "INSERT INTO devices (site, id, name, room, kind, rated_w, tier, sensitive, allow, is_on, normal_on, "
        "setpoint, signature_w, signature_measured, added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (site, s["device_id"], name.strip() or kind, room, kind, s["learned_w"], tier, int(sensitive),
         int(allow), 1, 1, 24 if kind == "ac" else None, s["learned_w"], 1, 1),
    )
    db.set_state(conn, f"learn:{site}", None)
    access = "T2 محمي" if tier == "T2" else ("T1 بالقائمة المسموحة" if allow else "تحكم يدوي فقط")
    room_name = db.one(conn.execute("SELECT name FROM rooms WHERE site=? AND id=?", (site, room)))["name"]
    db.audit(conn, site, "T0", "human", "device_added",
             f"جهاز جديد: {name} ({room_name}) · بصمة ≈ {s['learned_w']} واط · {access}")
    return db.device(conn, site, s["device_id"])


def cancel_learning(conn, site: str) -> None:
    db.set_state(conn, f"learn:{site}", None)
