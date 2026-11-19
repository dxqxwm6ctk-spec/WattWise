"""The agent loop (rule-based planner for now).

Every second, for each site, the agent:
  1. expires approval requests nobody answered (silence is not consent),
  2. checks the data is fresh, otherwise goes fail-safe,
  3. verifies executed actions with the meter (and learns the load signature),
  4. looks for waste and, if it finds some, proposes an action and asks the human.

The steps are written as small "tools" so the LLM planner (next phase) can call
the very same functions. The LLM will only choose and explain; the Policy Guard
and the approval flow stay in plain code.
"""

import time

from backend import actions, billing, config, db, policy

# Remembers what the agent is currently looking at, per site: {"device_id", "since"}
_analyzing: dict[str, dict] = {}


# ---------------- tools ----------------

def read_sensors(conn, site: str) -> dict:
    """Tool: latest meter and room readings."""
    return {
        "meter": db.latest_meter(conn, site),
        "rooms": {r["id"]: db.latest_room(conn, site, r["id"]) for r in db.rooms(conn, site)},
    }


def get_tariff(conn, site: str) -> dict:
    """Tool: price of the next kWh for this site's consumption this month."""
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    meter = db.latest_meter(conn, site)
    kwh = (meter or {}).get("energy_kwh") or 0.0
    return {"type": ttype, "price_jod_per_kwh": billing.marginal_price(kwh, tariff, ttype)}


def empty_for_seconds(conn, site: str, room_id: str, now: float) -> float | None:
    """How long the room's PIR has reported 'empty'. None if occupied or unknown."""
    latest = db.latest_room(conn, site, room_id)
    if not latest or latest["occupied"] is None or latest["occupied"]:
        return None
    row = conn.execute("SELECT MAX(ts) AS t FROM room_readings WHERE site=? AND room_id=? AND occupied=1",
                       (site, room_id)).fetchone()
    if row["t"] is None:
        row = conn.execute("SELECT MIN(ts) AS t FROM room_readings WHERE site=? AND room_id=?",
                           (site, room_id)).fetchone()
    return now - row["t"]


def detect_waste(conn, site: str, now: float) -> list[dict]:
    """Tool: devices that run in a room that has been empty for a while."""
    found = []
    for d in db.devices(conn, site):
        if not d["is_on"] or not d["allow"] or policy.is_critical(d) or d["sensitive"]:
            continue
        empty_s = empty_for_seconds(conn, site, d["room"], now)
        if empty_s is None or empty_s < config.WASTE_EMPTY_S:
            continue
        room = db.latest_room(conn, site, d["room"])
        found.append({"device": d, "room": room, "empty_s": empty_s,
                      "window_open": bool(room and room["window_open"])})
    # Biggest waste first.
    return sorted(found, key=lambda w: -w["device"]["signature_w"])


def recently_asked(conn, site: str, device_id: str, now: float) -> bool:
    row = conn.execute(
        "SELECT MAX(decided_ts) AS t FROM approvals WHERE site=? AND device_id=? AND status IN (?,?,?)",
        (site, device_id, actions.REJECTED, actions.EXPIRED, actions.BLOCKED)).fetchone()
    return row["t"] is not None and now - row["t"] < config.ASK_COOLDOWN_S


def explain(waste: dict, price: float) -> tuple[str, str, dict]:
    """Plain Arabic explanation with the numbers (reason, saving, alternative)."""
    d = waste["device"]
    minutes = max(1, round(waste["empty_s"] / 60))
    title = f"نطفي {d['name']}؟"
    if waste["window_open"] and d["kind"] in config.COOLING_KINDS:
        reason = "ما حدا بالغرفة من شوي والشباك مفتوح، يعني المكيّف عم يبرّد الشارع."
    else:
        reason = f"ما حدا بالغرفة من {minutes} دقيقة و{d['name']} شغّال."
    details = {
        "device": d["name"],
        "signature_w": round(d["signature_w"]),
        "signature_measured": bool(d["signature_measured"]),
        "saving_jod_per_hour": round(d["signature_w"] / 1000 * price, 3),
        "price_jod_per_kwh": price,
        "room_temp_c": (waste["room"] or {}).get("temp_c"),
        "alternative": "إذا رفضتي، بنخلّيه شغّال وما بنسأل عنه مرة ثانية لفترة.",
    }
    return title, reason, details


# ---------------- the loop ----------------

def tick(conn, site: str, now: float | None = None) -> None:
    now = now or time.time()
    estop = actions.flag(conn, "estop", site)

    # 1. Silence is not consent.
    a = actions.pending_approval(conn, site)
    if a and policy.approval_expired(a["created_ts"], now):
        actions.expire_approval(conn, a)

    # Learning a new device's signature (from the app's "add device" flow).
    actions.finish_learning_if_ready(conn, site)

    # 2. Fail-safe on stale data (sensor fault or lost connection).
    meter = db.latest_meter(conn, site)
    stale = meter is None or now - meter["ts"] > config.STALE_READING_S
    was_fault = actions.flag(conn, "fault", site)
    if stale:
        if meter is not None and not was_fault:
            db.set_state(conn, f"fault:{site}", True)
            actions._close_pending(conn, site, actions.CANCELLED)
            conn.execute("UPDATE devices SET is_on=normal_on, agent_off=0 WHERE site=? AND agent_off>0", (site,))
            db.audit(conn, site, "STOP", "system", "fail_safe",
                     "انقطعت القراءات ← وضع آمن: رجّعنا الأجهزة لوضعها الطبيعي وما في إجراء تلقائي.")
            actions.set_phase(conn, site, "offline")
        return
    if was_fault:
        db.set_state(conn, f"fault:{site}", False)
        db.audit(conn, site, "T0", "system", "recovered", "رجعت القراءات. الوكيل رجع يراقب.")
        if actions.get_phase(conn, site) == "offline" and not actions.flag(conn, "safe_mode", site):
            actions.set_phase(conn, site, "normal")

    # 3. Verify executed actions with the meter.
    _verify(conn, site, now)

    if estop or actions.flag(conn, "safe_mode", site):
        _analyzing.pop(site, None)
        return

    # 4. Plan: only when the human gave a goal, and one question at a time.
    if not actions.active_goal(conn, site) or actions.pending_approval(conn, site):
        return
    if actions.get_phase(conn, site) == "executing":
        return

    candidates = [w for w in detect_waste(conn, site, now)
                  if not recently_asked(conn, site, w["device"]["id"], now)]
    if not candidates:
        if site in _analyzing:
            _analyzing.pop(site)
            if actions.get_phase(conn, site) == "analyzing":
                actions.set_phase(conn, site, "normal")
        return

    waste = candidates[0]
    d = waste["device"]
    current = _analyzing.get(site)
    if not current or current["device_id"] != d["id"]:
        _analyzing[site] = {"device_id": d["id"], "since": now}
        room_name = _room_name(conn, site, d["room"])
        extra = "، وشباكها مفتوح" if waste["window_open"] else ""
        db.audit(conn, site, "T0", "agent", "waste_detected",
                 f"كشف هدر: {d['name']} شغّال و{room_name} فاضية{extra}. بنتأكد من حدود الراحة.")
        actions.set_phase(conn, site, "analyzing")
        return
    if now - current["since"] < config.ANALYZE_S:
        return

    # Ask the Policy Guard before even asking the human.
    decision = policy.check_switch(d, False, policy.AGENT, waste["room"], estop=estop)
    _analyzing.pop(site, None)
    if not decision.allowed:
        conn.execute(
            "INSERT INTO approvals (site, device_id, turn_on, created_ts, expires_ts, title, reason, status, decided_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (site, d["id"], 0, now, now, "blocked", decision.reason_ar, actions.BLOCKED, now))
        db.audit(conn, site, "T0", "policy", "proposal_blocked",
                 f"ما رح نقترح إطفاء {d['name']}: {decision.reason_ar}")
        actions.set_phase(conn, site, "normal")
        return

    price = get_tariff(conn, site)["price_jod_per_kwh"]
    title, reason, details = explain(waste, price)
    actions.request_approval(conn, site, d, False, title, reason, details)
    db.audit(conn, site, "T1", "agent", "proposal",
             f"اقتراح: إطفاء {d['name']} (−{round(d['signature_w'])} واط). بانتظار الموافقة.", details)


def _verify(conn, site: str, now: float) -> None:
    rows = db.rows(conn.execute(
        "SELECT * FROM approvals WHERE site=? AND status=? AND verified_ts IS NULL", (site, actions.APPROVED)))
    for a in rows:
        if now - a["decided_ts"] < config.VERIFY_AFTER_S:
            continue
        d = db.device(conn, site, a["device_id"])
        after = db.avg_power(conn, site, 1.5) or 0.0
        drop = (a["power_before"] or 0.0) - after
        conn.execute("UPDATE approvals SET power_after=?, verified_ts=? WHERE id=?", (after, now, a["id"]))
        if d and not a["turn_on"] and d["agent_off"] == actions.AGENT_OFF_UNVERIFIED:
            if drop > 0.5 * d["signature_w"] or (drop > 5 and not d["signature_measured"]):
                # NILM-lite: the measured step becomes the device's signature.
                db.set_device(conn, site, d["id"], signature_w=round(drop), signature_measured=1,
                              agent_off=actions.AGENT_OFF_VERIFIED)
                db.audit(conn, site, "OK", "agent", "verified",
                         f"العدّاد أكّد انخفاض ≈ {round(drop)} واط يطابق بصمة {d['name']}. بدأ حساب التوفير المُقاس.",
                         {"before_w": round(a["power_before"] or 0), "after_w": round(after)})
                actions.set_phase(conn, site, "verified")
            else:
                db.audit(conn, site, "T1", "agent", "verify_failed",
                         f"العدّاد ما بيّن انخفاض واضح ({round(drop)} واط). ما رح نحسب توفير لهالإجراء.",
                         {"before_w": round(a["power_before"] or 0), "after_w": round(after)})
                db.set_device(conn, site, d["id"], agent_off=actions.AGENT_OFF_NONE)
                actions.set_phase(conn, site, "normal")


def _room_name(conn, site: str, room_id: str) -> str:
    r = db.one(conn.execute("SELECT name FROM rooms WHERE site=? AND id=?", (site, room_id)))
    return r["name"] if r else room_id


def tick_all() -> None:
    with db.connect() as conn:
        for site in config.load_sites():
            tick(conn, site)
