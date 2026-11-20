"""The agent loop: rule-based planner, with an optional LLM planner on top.

Every second, for each site, the agent:
  1. expires approval requests nobody answered (silence is not consent),
  2. checks the data is fresh, otherwise goes fail-safe,
  3. verifies executed actions with the meter (and learns the load signature),
  4. looks for waste and, if it finds some, proposes an action and asks the human.

The steps are small "tools". When an LLM is configured (backend/llm.py) it
splits the goal into a plan and chooses/explains the proposal; the Policy Guard
and the approval flow stay in plain code, and the rules take over whenever the
LLM is missing, late, broken or over budget.
"""

import time
from concurrent.futures import Future, ThreadPoolExecutor

from backend import actions, alerts, billing, config, connectivity, db, ev, forecast, goal, llm, nilm, policy, schedules, weather

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
        if d["kind"] == "ev":   # a car charging in an empty garage is normal; handled by backend/ev.py
            continue
        empty_s = empty_for_seconds(conn, site, d["room"], now)
        if empty_s is None or empty_s < config.WASTE_EMPTY_S:
            continue
        room = db.latest_room(conn, site, d["room"])
        found.append({"device": d, "room": room, "empty_s": empty_s,
                      "window_open": bool(room and room["window_open"])})
    # Devices the goal named come first (backend/goal.py), then the biggest waste.
    plan = db.get_state(conn, f"plan:{site}", None)
    return sorted(found, key=lambda w: (goal.focus_rank(plan, w["device"]), -w["device"]["signature_w"]))


def recently_asked(conn, site: str, device_id: str, now: float) -> bool:
    row = conn.execute(
        "SELECT MAX(decided_ts) AS t FROM approvals WHERE site=? AND device_id=? AND status IN (?,?,?,?)",
        (site, device_id, actions.REJECTED, actions.EXPIRED, actions.BLOCKED, actions.SKIPPED)).fetchone()
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
        "alternative": ("سكّر الشباك وخلّي المكيّف شغّال، هيك ما بيبرّد الشارع."
                        if waste["window_open"] and d["kind"] in config.COOLING_KINDS
                        else "بنخلّيه شغّال وما بنسأل عنه مرة ثانية لفترة."),
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
            alerts.raise_alert(conn, site, "offline", "offline", alerts.DANGER, "انقطعت القراءات",
                               "ما وصلنا إشي من العدّاد. رجّعنا الأجهزة لوضعها الطبيعي.", now=now)
        return
    if was_fault:
        db.set_state(conn, f"fault:{site}", False)
        db.audit(conn, site, "T0", "system", "recovered", "رجعت القراءات. الوكيل رجع يراقب.")
        alerts.resolve(conn, site, "offline", now)
        if actions.get_phase(conn, site) == "offline" and not actions.flag(conn, "safe_mode", site):
            actions.set_phase(conn, site, "normal")

    # Timers and daily schedules the human set up (each one checked by the Policy Guard).
    schedules.run_due(conn, site)

    # 3. Verify executed actions with the meter.
    _verify(conn, site, now)
    forecast.track(conn, site)
    ev.track(conn, site, now)   # EV charging sessions: recognise, measure, notify

    # Warnings for the phone (tier 0: messages only, they also run during an emergency stop).
    alerts.check(conn, site, now)

    if estop or actions.flag(conn, "safe_mode", site):
        _analyzing.pop(site, None)
        _jobs.pop(site, None)
        return

    _llm_plan(conn, site, now)

    # 4. Plan: only when the human gave a goal, and one question at a time.
    if not actions.active_goal(conn, site) or actions.pending_approval(conn, site):
        return
    if actions.get_phase(conn, site) == "executing":
        return

    # Smart EV charging (evening peak): propose a pause, the human decides.
    if ev.maybe_propose(conn, site, now):
        return

    candidates = [w for w in detect_waste(conn, site, now)
                  if not recently_asked(conn, site, w["device"]["id"], now)]
    if not candidates:
        _jobs.pop(site, None)
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
        _jobs.pop(site, None)
        room_name = _room_name(conn, site, d["room"])
        extra = "، وشباكها مفتوح" if waste["window_open"] else ""
        db.audit(conn, site, "T0", "agent", "waste_detected",
                 f"كشف هدر: {d['name']} شغّال و{room_name} فاضية{extra}. بنتأكد من حدود الراحة.")
        actions.set_phase(conn, site, "analyzing")
        return
    if now - current["since"] < config.ANALYZE_S:
        return

    # Ask the Policy Guard before even asking the human (and before the LLM sees it).
    allowed = []
    for w in candidates:
        decision = policy.check_switch(w["device"], False, policy.AGENT, w["room"], estop=estop,
                                       plug=db.plug(conn, site, w["device"]["id"]))
        if decision.allowed:
            allowed.append(w)
        elif w is waste:
            _record_skip(conn, site, w["device"], actions.BLOCKED, decision.reason_ar, now)
            db.audit(conn, site, "T0", "policy", "proposal_blocked",
                     f"ما رح نقترح إطفاء {w['device']['name']}: {decision.reason_ar}")
    if waste not in allowed:
        _analyzing.pop(site, None)
        actions.set_phase(conn, site, "normal")
        return

    price = get_tariff(conn, site)["price_jod_per_kwh"]
    choice = _llm_choice(conn, site, now, allowed, price)
    if choice == "wait":
        return
    _analyzing.pop(site, None)

    if choice and choice["action"] == "none":
        _record_skip(conn, site, d, actions.SKIPPED, choice["reason"], now)
        db.audit(conn, site, "T0", "llm", "no_action", f"قرّرنا ما نقترح إشي هلأ: {choice['reason']}")
        actions.set_phase(conn, site, "normal")
        return

    if choice:
        picked = [w for w in allowed if w["device"]["id"] == choice["device_id"]]
        if picked:
            waste, d = picked[0], picked[0]["device"]
        else:  # the situation changed while the LLM was thinking
            choice = None
    title, reason, details = explain(waste, price)
    details["explained_by"] = "rules"
    if choice:
        title = choice["title"] or title
        reason = choice["reason"] or reason
        details["alternative"] = choice["alternative"] or details["alternative"]
        details["explained_by"] = "llm"
    actions.request_approval(conn, site, d, False, title, reason, details)
    db.audit(conn, site, "T1", "llm" if choice else "agent", "proposal",
             f"اقتراح: إطفاء {d['name']} (−{round(d['signature_w'])} واط). بانتظار الموافقة.", details)


def _record_skip(conn, site, d, status, reason, now) -> None:
    """A closed approval row, so the agent does not ask about this device again for a while."""
    conn.execute(
        "INSERT INTO approvals (site, device_id, turn_on, created_ts, expires_ts, title, reason, status, decided_ts) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (site, d["id"], 0, now, now, status, reason, status, now))


# ---------------- LLM layer (optional) ----------------
# The LLM runs in a background thread so the 1-second loop never blocks.
# It only reads a snapshot; its answer comes back here and goes through the
# same Policy Guard and approval flow as the rule-based planner.

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm")
_jobs: dict[str, dict] = {}        # decision jobs, per site
_plan_jobs: dict[str, dict] = {}   # goal-plan jobs, per site


def _submit(fn, *args) -> Future:
    return _executor.submit(fn, *args)


def snapshot(conn, site: str, now: float, wastes: list[dict], price: float) -> dict:
    """Everything the LLM may look at, as plain JSON (read-only copy)."""
    meter = db.latest_meter(conn, site) or {}
    rooms = []
    for r in db.rooms(conn, site):
        x = db.latest_room(conn, site, r["id"]) or {}
        rooms.append({"room_id": r["id"], "name": r["name"], "temp_c": x.get("temp_c"), "light": x.get("light"),
                      "occupied": x.get("occupied"), "window_open": x.get("window_open")})
    on = [{"device_id": d["id"], "name": d["name"], "room": d["room"], "kind": d["kind"],
           "watts": round(d["signature_w"])} for d in db.devices(conn, site) if d["is_on"]]
    tariff = get_tariff(conn, site)
    tariff["month_kwh"] = meter.get("energy_kwh")
    waste = [{"device_id": w["device"]["id"], "name": w["device"]["name"], "room": w["device"]["room"],
              "watts": round(w["device"]["signature_w"]),
              "watts_measured_by_meter": bool(w["device"]["signature_measured"]),
              "room_empty_minutes": round(w["empty_s"] / 60, 1), "window_open": w["window_open"],
              "room_temp_c": (w["room"] or {}).get("temp_c"),
              "saving_jod_per_hour": round(w["device"]["signature_w"] / 1000 * price, 3)} for w in wastes]
    return {"read_sensors": {"power_w": meter.get("power_w"), "rooms": rooms, "devices_on": on,
                             "comfort_c": [config.COMFORT_MIN_TEMP_C, config.COMFORT_MAX_TEMP_C]},
            "get_tariff": tariff, "detect_waste": waste, "forecast_load": forecast.cached(conn, site)}


def _finish(conn, site: str, job: dict, kind: str):
    """Collect a finished (or late) LLM job. Returns its answer, or None for fallback."""
    f: Future = job["future"]
    if not f.done():
        f.cancel()
        llm.mark_down()
        db.audit(conn, site, "T0", "system", "llm_fallback", f"النموذج تأخّر ({kind}). كمّلنا بالقواعد.")
        return None
    try:
        answer, result = f.result()
    except Exception as e:
        llm.mark_down()
        db.audit(conn, site, "T0", "system", "llm_fallback",
                 f"النموذج ما اشتغل ({kind}: {type(e).__name__}). كمّلنا بالقواعد.")
        return None
    llm.add_spend(conn, result)
    if answer is None:
        db.audit(conn, site, "T0", "system", "llm_fallback", f"جواب النموذج ما كان صالح ({kind}). كمّلنا بالقواعد.")
    return answer


def _llm_choice(conn, site: str, now: float, allowed: list[dict], price: float):
    """'wait' while the LLM thinks, its choice when done, None to use the rules."""
    job = _jobs.get(site)
    if job is None:
        if not llm.available(conn):
            return None
        goal = actions.active_goal(conn, site)
        snap = snapshot(conn, site, now, allowed, price)
        _jobs[site] = {"since": now, "future": _submit(llm.decide, llm.get_provider(), goal["text"], snap)}
        job = _jobs[site]
    if not job["future"].done() and now - job["since"] < config.LLM_TIMEOUT_S:
        return "wait"
    _jobs.pop(site, None)
    return _finish(conn, site, job, "اقتراح")


def _llm_plan(conn, site: str, now: float) -> None:
    """When a goal arrives, let the LLM split it into its own plan (rule plan stays until then)."""
    goal = actions.active_goal(conn, site)
    plan = db.get_state(conn, f"plan:{site}", None)
    if not goal or not plan or plan.get("goal_id") != goal["id"]:
        return
    job = _plan_jobs.get(site)
    if job is None:
        if plan.get("by") != "rules" or plan.get("llm_tried") or not llm.available(conn):
            return
        db.set_state(conn, f"plan:{site}", {**plan, "llm_tried": True})
        snap = snapshot(conn, site, now, [], get_tariff(conn, site)["price_jod_per_kwh"])
        _plan_jobs[site] = {"since": now, "goal_id": goal["id"],
                            "future": _submit(llm.plan_goal, llm.get_provider(), goal["text"],
                                              goal["bill_target_jd"], snap)}
        return
    if not job["future"].done() and now - job["since"] < config.LLM_TIMEOUT_S:
        return
    _plan_jobs.pop(site, None)
    answer = _finish(conn, site, job, "خطة")
    if answer and job["goal_id"] == goal["id"]:
        # Keep the rule-based reading of the goal (focus rooms/kinds) next to the LLM's own plan.
        current = db.get_state(conn, f"plan:{site}", None) or {}
        db.set_state(conn, f"plan:{site}", {"goal_id": goal["id"], "by": "llm", **answer,
                                             "intent": current.get("intent"), "focus": current.get("focus")})
        db.audit(conn, site, "T0", "llm", "plan", "النموذج قسّم الهدف لخطة: " + " · ".join(answer["steps"]),
                 {"steps": answer["steps"], "summary": answer["summary"]})


def _verify(conn, site: str, now: float) -> None:
    rows = db.rows(conn.execute(
        "SELECT * FROM approvals WHERE site=? AND status=? AND verified_ts IS NULL", (site, actions.APPROVED)))
    for a in rows:
        if now - a["decided_ts"] < config.VERIFY_AFTER_S:
            continue
        d = db.device(conn, site, a["device_id"])
        plug = db.plug(conn, site, a["device_id"])
        if plug and plug["meters"] and plug["online"] and (plug["last_seen_ts"] or 0) <= a["decided_ts"]:
            continue   # wait for a fresh reading from the device's own smart plug
        after = actions.power_now(conn, site, a["device_id"], 1.5)
        if after is None:
            continue   # no fresh reading yet: an empty window would look like a huge drop
        drop = (a["power_before"] or 0.0) - after
        conn.execute("UPDATE approvals SET power_after=?, verified_ts=? WHERE id=?", (after, now, a["id"]))
        if d and not a["turn_on"] and d["agent_off"] == actions.AGENT_OFF_UNVERIFIED:
            if drop > 0.5 * d["signature_w"] or (drop > 5 and not d["signature_measured"]):
                # NILM-lite: the measured step (watts + power factor) becomes the device's signature.
                pf = _step_pf(conn, site, a, now, drop)
                same_type = nilm.pf_matches(d["signature_pf"], pf)
                db.set_device(conn, site, d["id"], signature_w=round(drop), signature_measured=1,
                              signature_pf=pf if pf is not None else d["signature_pf"],
                              agent_off=actions.AGENT_OFF_VERIFIED)
                pf_text = ""
                if pf is not None:
                    pf_text = f" · PF {pf:.2f}، {nilm.load_type_ar(pf)}"
                    if same_type is False:
                        pf_text += f" (كان {d['signature_pf']:.2f}، يمكن الجهاز تغيّر)"
                db.audit(conn, site, "OK", "agent", "verified",
                         f"العدّاد أكّد انخفاض ≈ {round(drop)} واط يطابق بصمة {d['name']}{pf_text}. "
                         + ("هاد تأجيل للشحن مش توفير، فما بنحسبه بالتوفير." if d["kind"] == "ev"
                            else "بدأ حساب التوفير المُقاس."),
                         {"before_w": round(a["power_before"] or 0), "after_w": round(after), "step_pf": pf})
                actions.set_phase(conn, site, "verified")
            else:
                db.audit(conn, site, "T1", "agent", "verify_failed",
                         f"العدّاد ما بيّن انخفاض واضح ({round(drop)} واط). ما رح نحسب توفير لهالإجراء.",
                         {"before_w": round(a["power_before"] or 0), "after_w": round(after)})
                db.set_device(conn, site, d["id"], agent_off=actions.AGENT_OFF_NONE)
                actions.set_phase(conn, site, "normal")


def _step_pf(conn, site: str, approval: dict, now: float, drop_w: float) -> float | None:
    """Power factor of the switched device: reactive power before the switch minus after it."""
    t = approval["decided_ts"]
    _, q_before = db.avg_pq(conn, site, t - 3, t)
    _, q_after = db.avg_pq(conn, site, now - 1.5, now)
    if q_before is None or q_after is None:
        return None
    return nilm.step_pf(drop_w, q_before - q_after)


def _room_name(conn, site: str, room_id: str) -> str:
    r = db.one(conn.execute("SELECT name FROM rooms WHERE site=? AND id=?", (site, room_id)))
    return r["name"] if r else room_id


def note_internet_changes(conn) -> None:
    """Write 'internet lost / back' into every site's audit log (the judges see it live)."""
    for ch in connectivity.pop_changes():
        sim = " (محاكاة للتجربة)" if ch["forced"] else ""
        for site in config.load_sites():
            if ch["online"]:
                db.audit(conn, site, "T0", "system", "internet_back",
                         f"رجع الإنترنت{sim}. الطقس والنموذج رجعوا متاحين، وما ضاع إشي من القياس.")
            else:
                db.audit(conn, site, "T0", "system", "internet_lost",
                         f"انقطع الإنترنت{sim} ← WattWise مكمّل محليًا: قياس، كشف هدر، موافقة، إطفاء، تحقق.")


def tick_all() -> None:
    connectivity.check_in_background()
    weather.refresh_in_background()
    with db.connect() as conn:
        note_internet_changes(conn)
        for site in config.load_sites():
            tick(conn, site)
