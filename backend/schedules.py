"""Timers and daily schedules (on/off only), plus the smart water-heater schedule.

- A *timer* runs once: "switch the fan off after 30 minutes".
- A *schedule* repeats every day: "heater on at 05:30, off at 06:30".

The human sets them up (from the dashboard, the phone or a spoken command), so
they count as already approved. But the Policy Guard checks each one twice: when
it is saved (check_schedule / check_timer) and again at the moment it fires
(check_switch with actor=SCHEDULE: no critical or sensitive loads, nothing during
an emergency stop or safe mode, comfort limits still hold). Every firing goes to
the audit log.

All times are on the *site clock* (the meter's clock). The simulator runs 60x
faster, so in the demo "after 30 minutes" takes 30 real seconds.
"""

import re
import time

from backend import billing, config, db, policy
from backend.actions import ActionError, flag, require_device, require_site

TIER = "SCHED"   # audit-log tier for timers and schedules


# ---------- the site clock ----------

def site_now(conn, site: str) -> float:
    """The latest meter timestamp (the simulator's fast clock, or real time on the ESP32)."""
    m = db.latest_meter(conn, site)
    return m["meter_ts"] if m else time.time()


def last_occurrence(now_ts: float, hhmm: str) -> float:
    """The most recent moment (<= now) the clock showed hhmm."""
    t = time.localtime(now_ts)
    now_min = t.tm_hour * 60 + t.tm_min
    back_min = (now_min - policy._minutes(hhmm)) % 1440
    return now_ts - back_min * 60 - t.tm_sec


def fmt_minutes(n: int) -> str:
    """30 -> "30 دقيقة", 60 -> "ساعة", 150 -> "2 س و 30 د"."""
    if n < 60:
        return f"{n} دقيقة"
    if n == 60:
        return "ساعة"
    if n == 120:
        return "ساعتين"
    if n % 60 == 0:
        return f"{n // 60} ساعات"
    return f"{n // 60} س و {n % 60} د"


def normalize_time(value: str | None) -> str | None:
    """"6:5" -> "06:05". Empty -> None. Bad -> the original text (the guard rejects it)."""
    if value is None or str(value).strip() == "":
        return None
    m = policy._minutes(value)
    return value if m is None else f"{m // 60:02d}:{m % 60:02d}"


# ---------- days of the week ----------

# 0 = Sunday ... 6 = Saturday (the same numbers as JavaScript's getDay()).
DAY_NAMES = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]


def normalize_days(days) -> str | None:
    """[0, 4, 4] -> "04". None, or all seven days -> None (means every day)."""
    if days is None:
        return None
    try:
        picked = sorted({int(x) for x in days})
    except (TypeError, ValueError):
        raise ActionError("الأيام مش مفهومة.")
    if not picked:
        raise ActionError("اختار يوم واحد على الأقل.")
    if any(x < 0 or x > 6 for x in picked):
        raise ActionError("الأيام مش مفهومة.")
    return None if len(picked) == 7 else "".join(str(x) for x in picked)


def days_text(days: str | None) -> str:
    if not days:
        return "كل يوم"
    if days == "01234":
        return "الأحد للخميس"
    if days == "56":
        return "الجمعة والسبت"
    return "، ".join(DAY_NAMES[int(x)] for x in days)


def weekday(ts: float) -> int:
    """0 = Sunday ... 6 = Saturday, on the site clock."""
    return (time.localtime(ts).tm_wday + 1) % 7


def runs_on(days: str | None, ts: float) -> bool:
    return not days or str(weekday(ts)) in days


# ---------- estimates (expected, never shown as a measured saving) ----------

def estimate_day(conn, site: str, device: dict, on_time: str | None, off_time: str | None) -> dict | None:
    """Expected energy and cost per day of an on->off window, from the load signature."""
    if not (on_time and off_time):
        return None
    minutes = policy.window_minutes(on_time, off_time)
    kwh = device["signature_w"] * minutes / 60 / 1000
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    meter = db.latest_meter(conn, site) or {}
    price = billing.marginal_price(meter.get("energy_kwh") or 0.0, tariff, ttype)
    return {"kwh": round(kwh, 2), "jod": round(kwh * price, 3)}


# ---------- create / list / change ----------

def _room_name(conn, site: str, room_id: str) -> str:
    r = db.one(conn.execute("SELECT name FROM rooms WHERE site=? AND id=?", (site, room_id)))
    return r["name"] if r else room_id


def preview_schedule(conn, site: str, device_id: str, on_time: str | None, off_time: str | None,
                     days=None) -> dict:
    """The review step before saving: the guard checks it and we show what will happen. Saves nothing."""
    require_site(site)
    d = require_device(conn, site, device_id)
    on_time, off_time = normalize_time(on_time), normalize_time(off_time)
    days = normalize_days(days)
    decision = policy.check_schedule(d, on_time, off_time)
    if not decision.allowed:
        raise ActionError(decision.reason_ar)
    when = " ← ".join(x for x in (on_time and f"يشتغل {on_time}", off_time and f"يطفي {off_time}") if x)
    return {"device_id": d["id"], "device_name": d["name"], "room_name": _room_name(conn, site, d["room"]),
            "on_time": on_time, "off_time": off_time, "days": days, "days_text": days_text(days),
            "text": f"{d['name']} ({_room_name(conn, site, d['room'])}): {when} · {days_text(days)}",
            "estimate": estimate_day(conn, site, d, on_time, off_time)}


def add_schedule(conn, site: str, device_id: str, on_time: str | None, off_time: str | None,
                 source: str = "user", days=None) -> dict:
    require_site(site)
    d = require_device(conn, site, device_id)
    on_time, off_time = normalize_time(on_time), normalize_time(off_time)
    days = normalize_days(days)
    decision = policy.check_schedule(d, on_time, off_time)
    if not decision.allowed:
        if decision.code in ("heater_too_long", "critical_load", "sensitive_device"):
            db.audit(conn, site, "T0", "policy", "blocked", f"{decision.reason_ar} ← الجدول ما انحفظ.")
        raise ActionError(decision.reason_ar)
    cur = conn.execute(
        "INSERT INTO schedules (site, device_id, on_time, off_time, days, enabled, source, created_ts) "
        "VALUES (?,?,?,?,?,1,?,?)", (site, device_id, on_time, off_time, days, source, time.time()))
    when = " · ".join(x for x in (on_time and f"تشغيل {on_time}", off_time and f"إطفاء {off_time}") if x)
    db.audit(conn, site, TIER, "human", "schedule_added",
             f"جدول جديد: {d['name']} ({_room_name(conn, site, d['room'])}) · {when} · {days_text(days)}.")
    return {"id": cur.lastrowid}


def add_timer(conn, site: str, device_id: str, minutes: int, turn_on: bool, run_now: bool = False) -> dict:
    """A one-off timer. run_now=True means "run it FOR n minutes": switch on now, off later."""
    require_site(site)
    d = require_device(conn, site, device_id)
    decision = policy.check_timer(d, minutes)
    if not decision.allowed:
        raise ActionError(decision.reason_ar)
    if run_now:
        _switch(conn, site, d, True, f"شغّلنا {d['name']} لمدة {fmt_minutes(minutes)} ← بينطفي لحاله بعدها.",
                actor="human")
    due = site_now(conn, site) + minutes * 60
    cur = conn.execute(
        "INSERT INTO timers (site, device_id, turn_on, due_ts, minutes, created_ts) VALUES (?,?,?,?,?,?)",
        (site, device_id, int(turn_on), due, minutes, time.time()))
    if not run_now:
        db.audit(conn, site, TIER, "human", "timer_added",
                 f"مؤقّت: {'تشغيل' if turn_on else 'إطفاء'} {d['name']} بعد {fmt_minutes(minutes)}.")
    return {"id": cur.lastrowid}


def set_enabled(conn, site: str, schedule_id: int, enabled: bool) -> None:
    conn.execute("UPDATE schedules SET enabled=? WHERE site=? AND id=?", (int(enabled), site, schedule_id))


def delete_schedule(conn, site: str, schedule_id: int) -> None:
    conn.execute("DELETE FROM schedules WHERE site=? AND id=?", (site, schedule_id))


def delete_timer(conn, site: str, timer_id: int) -> None:
    conn.execute("DELETE FROM timers WHERE site=? AND id=?", (site, timer_id))


def clear_all(conn, site: str) -> None:
    """Used by the demo reset."""
    conn.execute("DELETE FROM schedules WHERE site=?", (site,))
    conn.execute("DELETE FROM timers WHERE site=?", (site,))


def listing(conn, site: str) -> dict:
    """What the dashboard and the phone show.

    devices = the ones a schedule may switch; locked = the ones the guard never
    lets a schedule touch (critical or sensitive), shown with the reason.
    Every device carries its room, so the screens can group them by room.
    """
    require_site(site)
    names = {d["id"]: d for d in db.devices(conn, site)}
    room_names = {r["id"]: r["name"] for r in db.rooms(conn, site)}
    now = site_now(conn, site)
    out_s, out_t = [], []
    for r in db.rows(conn.execute("SELECT * FROM schedules WHERE site=? ORDER BY id", (site,))):
        d = names.get(r["device_id"])
        if not d:
            continue
        out_s.append({"id": r["id"], "device_id": r["device_id"], "device_name": d["name"],
                      "room": d["room"], "room_name": room_names.get(d["room"], d["room"]),
                      "on_time": r["on_time"], "off_time": r["off_time"], "enabled": bool(r["enabled"]),
                      "days": r["days"], "days_text": days_text(r["days"]),
                      "source": r["source"], "estimate": estimate_day(conn, site, d, r["on_time"], r["off_time"])})
    for t in db.rows(conn.execute("SELECT * FROM timers WHERE site=? ORDER BY due_ts", (site,))):
        d = names.get(t["device_id"])
        if not d:
            continue
        left = max(0, round((t["due_ts"] - now) / 60))
        out_t.append({"id": t["id"], "device_id": t["device_id"], "device_name": d["name"],
                      "turn_on": bool(t["turn_on"]), "minutes_left": left,
                      "text": f"{'تشغيل' if t['turn_on'] else 'إطفاء'} {d['name']} بعد {fmt_minutes(left)}"})
    def card(d):
        return {"id": d["id"], "name": d["name"], "kind": d["kind"], "room": d["room"],
                "room_name": room_names.get(d["room"], d["room"]), "is_on": bool(d["is_on"]),
                "watts": round(d["signature_w"])}
    devices, locked = [], []
    for d in names.values():
        decision = policy.check_timer(d, 1)
        if decision.allowed:
            devices.append(card(d))
        else:
            locked.append({**card(d), "why": decision.reason_ar})
    rooms = [{"id": rid, "name": name} for rid, name in room_names.items()]
    return {"site": site, "schedules": out_s, "timers": out_t, "devices": devices, "locked": locked,
            "rooms": rooms}


# ---------- running them (called by the agent loop every second) ----------

def _switch(conn, site: str, d: dict, turn_on: bool, message: str, actor: str = "schedule") -> bool:
    """Switch one device for a timer/schedule, through the Policy Guard. Returns True if done."""
    if bool(d["is_on"]) == turn_on:
        return False
    if actor == "human":
        decision = policy.check_switch(d, turn_on, policy.HUMAN, None, plug=db.plug(conn, site, d["id"]))
    else:
        decision = policy.check_switch(d, turn_on, policy.SCHEDULE, db.latest_room(conn, site, d["room"]),
                                       estop=flag(conn, "estop", site), safe_mode=flag(conn, "safe_mode", site),
                                       plug=db.plug(conn, site, d["id"]))
    if not decision.allowed:
        db.audit(conn, site, "T0", "policy", "schedule_blocked",
                 f"{message} ← حارس السياسات رفض: {decision.reason_ar}")
        return False
    db.set_device(conn, site, d["id"], is_on=int(turn_on), agent_off=0)
    db.audit(conn, site, TIER, actor, "schedule_fired", message)
    return True


def run_due(conn, site: str) -> None:
    now = site_now(conn, site)
    last = db.get_state(conn, f"sched_clock:{site}", None)
    db.set_state(conn, f"sched_clock:{site}", now)

    # One-off timers.
    for t in db.rows(conn.execute("SELECT * FROM timers WHERE site=? AND due_ts<=?", (site, now))):
        conn.execute("DELETE FROM timers WHERE id=?", (t["id"],))
        d = db.device(conn, site, t["device_id"])
        if d:
            verb = "تشغيل" if t["turn_on"] else "إطفاء"
            _switch(conn, site, d, bool(t["turn_on"]), f"مؤقّت: {verb} {d['name']}.")

    # Daily schedules: did the clock pass an on/off time since the last check?
    if last is None or now <= last:
        return
    for r in db.rows(conn.execute("SELECT * FROM schedules WHERE site=? AND enabled=1", (site,))):
        d = db.device(conn, site, r["device_id"])
        if not d:
            continue
        for hhmm, turn_on in ((r["on_time"], True), (r["off_time"], False)):
            if not (hhmm and policy._minutes(hhmm) is not None):
                continue
            when = last_occurrence(now, hhmm)
            if not last < when <= now:
                continue
            # Days: an off time after midnight belongs to the day the window started.
            day_ts = when
            if not turn_on and r["on_time"] and policy._minutes(hhmm) < (policy._minutes(r["on_time"]) or 0):
                day_ts = when - 86400
            if runs_on(r["days"], day_ts):
                verb = "تشغيل" if turn_on else "إطفاء"
                _switch(conn, site, d, turn_on, f"جدول: {verb} {d['name']} ({hhmm}).")
                d = db.device(conn, site, r["device_id"])


# ---------- smart water-heater schedule (rule-based) ----------

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def shower_times(hint: str) -> list[int]:
    """Read shower times from free Arabic text, as minutes after midnight.

    "الصبح ٦ ونص والمسا ٩" -> [390, 1260]. Words for evening (المسا / الليل / بالليل)
    move a small hour to the afternoon. ونص = :30, وربع = :15, الا ربع = :45 before.
    """
    text = (hint or "").translate(_AR_DIGITS)
    out = []
    for m in re.finditer(r"(\d{1,2})(?::(\d{2}))?(\s*(?:و\s*نص|ونص|و\s*ربع|وربع|الا\s*ربع|إلا\s*ربع))?", text):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        extra = (m.group(3) or "").replace(" ", "")
        if "نص" in extra:
            mi = 30
        elif "الاربع" in extra or "إلاربع" in extra:
            h, mi = h - 1, 45
        elif "ربع" in extra:
            mi = 15
        before = text[max(0, m.start() - 12):m.start()]
        if h < 12 and re.search(r"مسا|مساء|ليل|العصر|بعد الظهر", before):
            h += 12
        if 0 <= h < 24 and 0 <= mi < 60:
            out.append(h * 60 + mi)
    return out


def suggest_heater(conn, site: str, hint: str) -> dict:
    """Heat the tank in the hour BEFORE each shower, and keep the heater off the rest of the day."""
    require_site(site)
    heater = next((d for d in db.devices(conn, site) if d["kind"] == "heater"
                   and policy.check_timer(d, 1).allowed), None)
    if not heater:
        raise ActionError("ما في سخّان ماء بهذا الموقع.")
    times = sorted(set(shower_times(hint)))[:3]
    if times:
        reply = "بنسخّن المي بالساعة اللي قبل كل حمّام بس، والباقي بيضل مطفي."
        windows = [((t - 60) % 1440, t, "مي سخنة قبل الحمّام") for t in times]
    else:
        reply = "ما ذكرت أوقات، فهاد جدول افتراضي: الصبح والمسا. عدّله بكيفك."
        windows = [(330, 390, "مي سخنة قبل الحمّام الصبح"), (1200, 1260, "مي سخنة للمسا")]
    items, used = [], []
    for start, end, why in windows:
        if any(start < u_end and u_start < end for u_start, u_end in used):
            continue   # overlaps a window we already have (two showers close together)
        on_t, off_t = f"{start // 60:02d}:{start % 60:02d}", f"{end // 60:02d}:{end % 60:02d}"
        if not policy.check_schedule(heater, on_t, off_t).allowed:
            continue
        used.append((start, end))
        items.append({"on_time": on_t, "off_time": off_t, "why": why,
                      "estimate": estimate_day(conn, site, heater, on_t, off_t)})
    total_kwh = round(sum(i["estimate"]["kwh"] for i in items), 2)
    total_jod = round(sum(i["estimate"]["jod"] for i in items), 3)
    return {"device_id": heater["id"], "device_name": heater["name"], "reply": reply, "items": items,
            "total": {"kwh": total_kwh, "jod": total_jod}, "by": "rules"}


def apply_heater(conn, site: str, device_id: str, windows: list[dict]) -> dict:
    """Save the heater windows the human confirmed (replaces the heater's old schedules)."""
    d = require_device(conn, site, device_id)
    if d["kind"] != "heater":
        raise ActionError("هذا الجهاز مش سخّان.")
    if not windows or len(windows) > 3:
        raise ActionError("لازم من فترة لـ ٣ فترات.")
    for w in windows:   # check all first, so we never save half of it
        decision = policy.check_schedule(d, normalize_time(w.get("on_time")), normalize_time(w.get("off_time")))
        if not decision.allowed:
            raise ActionError(decision.reason_ar)
    conn.execute("DELETE FROM schedules WHERE site=? AND device_id=?", (site, device_id))
    for w in windows:
        conn.execute(
            "INSERT INTO schedules (site, device_id, on_time, off_time, enabled, source, created_ts) "
            "VALUES (?,?,?,?,1,'suggested',?)",
            (site, device_id, normalize_time(w["on_time"]), normalize_time(w["off_time"]), time.time()))
    spans = "، ".join(f"{normalize_time(w['on_time'])}–{normalize_time(w['off_time'])}" for w in windows)
    db.audit(conn, site, TIER, "human", "heater_schedule", f"جدول السخّان الذكي: {spans}. أكّدته إنت.")
    return {"ok": True}
