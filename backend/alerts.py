"""Warning notifications from the agent (tier 0: a message only, nothing is switched).

Every second the agent loop calls `check()`. It looks at the latest readings and
raises short Arabic warnings for the phone app and the dashboard:

  overload / current_high   the current is near the limit of the meter, the relay
                            or the circuit (danger)
  high_power                the house uses a lot of power right now
  tier_near                 this month's kWh are close to the next, more expensive tier
  left_on                   a device has been on for too long (water heater, washer...)
  unknown_device / anomaly  reused from anomaly detection (backend/anomaly.py)

A warning may carry an action ("طفّيه؟"). Pressing it does NOT switch anything:
it only creates a normal approval request, which then goes through the Policy
Guard and the human's Approve / Reject like every other agent action.

One row per warning in the `alerts` table. While its condition is still true the
row stays `active`, so the phone is notified once, not every second. After it
clears, the same warning can come back only after ALERT_COOLDOWN_S.

Other parts of the code can raise their own warnings with `raise_alert()` and
clear them with `resolve()` (for example, room appliance learning can raise an
"unknown_device" warning).
"""

import calendar
import time

from backend import actions, billing, config, db, policy

INFO, WARN, DANGER = "info", "warn", "danger"

# The current alert has two levels, as a fraction of the site's max_current_a.
CURRENT_WARN_FRAC = 0.8
CURRENT_DANGER_FRAC = 0.9
# "High consumption": above this fraction of the site's gauge maximum (labels.max_w) ...
HIGH_POWER_FRAC = 0.75
# ... for this many readings in a row (so a short spike, like a kettle, is ignored).
HIGH_POWER_READINGS = 10
# "Close to the next tier": warn at 80 % of the tier (heads-up) and again at 95 % (last call).
TIER_WARN_FRACS = (0.8, 0.95)
# Hours (on the site clock) after which a device of this kind counts as "left on too long".
LEFT_ON_LIMIT_H = {"heater": 2, "washer": 3, "tv": 6}


# ---------------- raising and clearing ----------------

def raise_alert(conn, site: str, key: str, kind: str, level: str, title: str, body: str,
                device_id: str | None = None, now: float | None = None) -> int | None:
    """Open a warning, unless the same one is already open or was closed a moment ago.

    key: what makes two warnings "the same" (for example "left_on:heater").
    Returns the new alert id, or None if nothing new was raised.
    """
    now = now or time.time()
    last = db.one(conn.execute(
        "SELECT id, active, ended_ts FROM alerts WHERE site=? AND key=? ORDER BY id DESC LIMIT 1", (site, key)))
    if last and (last["active"] or now - (last["ended_ts"] or 0) < config.ALERT_COOLDOWN_S):
        return None
    cur = conn.execute(
        "INSERT INTO alerts (site, ts, clock, key, kind, level, title, body, device_id, active) "
        "VALUES (?,?,?,?,?,?,?,?,?,1)",
        (site, now, db.site_clock(conn, site), key, kind, level, title, body, device_id))
    db.audit(conn, site, "T0", "agent", "alert", f"تنبيه للهاتف: {title} {body}",
             {"kind": kind, "level": level, "device_id": device_id})
    return cur.lastrowid


def resolve(conn, site: str, key: str, now: float | None = None) -> None:
    """The condition behind this warning is gone."""
    conn.execute("UPDATE alerts SET active=0, ended_ts=? WHERE site=? AND key=? AND active=1",
                 (now or time.time(), site, key))


def resolve_all(conn, site: str) -> None:
    conn.execute("UPDATE alerts SET active=0, ended_ts=? WHERE site=? AND active=1", (time.time(), site))


# ---------------- the checks (called every second) ----------------

def check(conn, site: str, now: float | None = None) -> None:
    now = now or time.time()
    meter = db.latest_meter(conn, site)
    if not meter:
        return
    found: dict[str, dict] = {}   # key -> alert, everything that is true right now
    for rule in (_current, _high_power, _tier, _anomaly, _left_on):
        for a in rule(conn, site, meter, found):
            found[a["key"]] = a

    for a in found.values():
        raise_alert(conn, site, a["key"], a["kind"], a["level"], a["title"], a["body"], a.get("device_id"), now)
    # Our own keys that are no longer true get closed. Keys raised by other modules are left alone.
    for row in db.rows(conn.execute("SELECT key FROM alerts WHERE site=? AND active=1", (site,))):
        if row["key"].split(":")[0] in OWN_KEYS and row["key"] not in found:
            resolve(conn, site, row["key"], now)


def _current_a(meter: dict) -> float | None:
    if meter.get("current_a") is not None:
        return meter["current_a"]
    if meter.get("power_w") and meter.get("voltage_v"):
        return meter["power_w"] / meter["voltage_v"]
    return None


def _biggest_switchable(conn, site: str) -> dict | None:
    """The biggest device that is on and that the agent could propose to switch off."""
    best = None
    for d in db.devices(conn, site):
        if not d["is_on"] or not d["allow"] or d["sensitive"] or policy.is_critical(d):
            continue
        if best is None or d["signature_w"] > best["signature_w"]:
            best = d
    return best


def _current(conn, site, meter, found):
    limit = (config.load_sites()[site].get("limits") or {}).get("max_current_a")
    amps = _current_a(meter)
    if not limit or amps is None or amps < limit * CURRENT_WARN_FRAC:
        return []
    big = _biggest_switchable(conn, site)
    hint = f" أكبر جهاز يعمل: {big['name']} (≈ {round(big['signature_w'])} واط)." if big else ""
    if amps >= limit * CURRENT_DANGER_FRAC:
        return [{"key": "current", "kind": "overload", "level": DANGER, "title": "⚡ خطر: حمل زائد!",
                 "body": f"التيار {amps:.1f} أمبير والحد {limit:g}. أطفئ جهازًا كبيرًا الآن.{hint}",
                 "device_id": big and big["id"]}]
    return [{"key": "current", "kind": "current_high", "level": DANGER, "title": "⚡ التيار يقترب من الحد",
             "body": f"التيار {amps:.1f} أمبير من أصل {limit:g}. لا تشغّل جهازًا كبيرًا الآن.{hint}",
             "device_id": big and big["id"]}]


def _high_power(conn, site, meter, found):
    if "current" in found:        # the danger warning already says it
        return []
    max_w = (config.load_sites()[site].get("labels") or {}).get("max_w")
    if not max_w:
        return []
    limit = max_w * HIGH_POWER_FRAC
    rows = conn.execute("SELECT power_w FROM meter_readings WHERE site=? ORDER BY id DESC LIMIT ?",
                        (site, HIGH_POWER_READINGS)).fetchall()
    if len(rows) < HIGH_POWER_READINGS or any(r["power_w"] < limit for r in rows):
        return []
    big = _biggest_switchable(conn, site)
    hint = f" أكبر جهاز يعمل: {big['name']}." if big else ""
    return [{"key": "high_power", "kind": "high_power", "level": WARN, "title": "استهلاك مرتفع الآن",
             "body": f"يستهلك البيت الآن ≈ {round(meter['power_w'])} واط.{hint}",
             "device_id": big and big["id"]}]


def _tier(conn, site, meter, found):
    """Warn BEFORE this month's kWh cross into the next, more expensive tier.

    Two steps: at TIER_WARN_FRACS[0] of the tier (early heads-up) and at
    TIER_WARN_FRACS[1] (last call). Each says when we will cross at this month's
    pace and which device used the most energy (the best thing to cut).
    """
    kwh = meter.get("energy_kwh")
    if kwh is None:
        return []
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    tiers = billing._tiers(tariff, ttype)
    for i, (cap, price) in enumerate(tiers[:-1]):
        if kwh > cap:
            continue
        frac = kwh / cap
        if frac < TIER_WARN_FRACS[0]:
            return []
        last_call = frac >= TIER_WARN_FRACS[1]
        left = cap - kwh
        nxt = round(tiers[i + 1][1] * 1000)
        now_fils = round(price * 1000)

        # When will we cross, at this month's average pace? (site clock)
        t = time.localtime(meter["meter_ts"])
        elapsed_days = max(0.5, t.tm_mday - 1 + (t.tm_hour + t.tm_min / 60) / 24)
        per_day = kwh / elapsed_days
        when = ""
        if per_day > 0:
            days = left / per_day
            if days < 1:
                when = " بهذا المعدّل ستدخلها اليوم."
            else:
                day = t.tm_mday + int(days)
                month_days = calendar.monthrange(t.tm_year, t.tm_mon)[1]
                when = (f" بهذا المعدّل ستدخلها بعد ≈ {days:.0f} يوم (يوم {day} من الشهر)."
                        if day <= month_days else " بهذا المعدّل قد ينتهي الشهر قبل أن تصلها.")

        # What to cut: the switchable device that used the most energy this month.
        top = None
        for d in db.devices(conn, site):
            if d["allow"] and not d["sensitive"] and not policy.is_critical(d) and d["energy_wh"] > 0:
                if top is None or d["energy_wh"] > top["energy_wh"]:
                    top = d
        cut = f" أكثر الأجهزة استهلاكًا: {top['name']}، فخفّف استخدامه." if top else ""

        title = ("تنبيه أخير: الشريحة الأغلى قريبة جدًا" if last_call
                 else f"بلغت {frac * 100:.0f}% من الشريحة الأولى" if i == 0
                 else f"بلغت {frac * 100:.0f}% من الشريحة")
        ratio = nxt / now_fils
        dearer = ("أي أن كل ك.و.س بعدها بضعف السعر" if abs(ratio - 2) < 0.05
                  else f"أي أن كل ك.و.س بعدها أغلى بـ{(ratio - 1) * 100:.0f}%")
        body = f"بقي {left:.0f} ك.و.س على دخول شريحة {nxt} فلس بدل {now_fils}، {dearer}.{when}{cut}"
        step = "last" if last_call else "early"
        return [{"key": f"tier:{cap:g}:{step}", "kind": "tier_near", "level": DANGER if last_call else WARN,
                 "title": title, "body": body, "device_id": top and top["id"]}]
    return []


def _anomaly(conn, site, meter, found):
    st = db.get_state(conn, f"anomaly:{site}", None) or {}
    if not st.get("open"):
        return []
    key = f"anomaly:{round(st.get('since') or 0)}"
    if st.get("kind") == "extra":
        return [{"key": key, "kind": "unknown_device", "level": WARN, "title": "هل بدأ جهاز غير معروف بالعمل؟",
                 "body": f"يقرأ العدّاد ≈ {st.get('residual_w')} واط زيادة عن الأجهزة المعروفة."}]
    return [{"key": key, "kind": "anomaly", "level": WARN, "title": "استهلاك أقل من المتوقع",
             "body": f"أقل بنحو {-(st.get('residual_w') or 0)} واط. ربما يوجد جهاز مفصول أو معطّل."}]


def _left_on(conn, site, meter, found):
    """Remembers since when each device is on (site clock) and warns after LEFT_ON_LIMIT_H."""
    t = meter["meter_ts"]
    since = db.get_state(conn, f"on_since:{site}", {}) or {}
    out, new_since = [], {}
    for d in db.devices(conn, site):
        if not d["is_on"]:
            continue
        new_since[d["id"]] = since.get(d["id"], t)
        limit_h = LEFT_ON_LIMIT_H.get(d["kind"])
        hours = (t - new_since[d["id"]]) / 3600
        if limit_h and hours >= limit_h:
            out.append({"key": f"left_on:{d['id']}", "kind": "left_on", "level": WARN,
                        "title": f"{d['name']} يعمل منذ مدة طويلة",
                        "body": f"يعمل منذ {hours:.1f} ساعة. هل نسيته؟",
                        "device_id": d["id"]})
    db.set_state(conn, f"on_since:{site}", new_since)
    return out


OWN_KEYS = {"current", "high_power", "tier", "anomaly", "left_on"}


# ---------------- for the UI ----------------

def _can_act(conn, site: str, a: dict) -> bool:
    """Show the "طفّيه؟" button only if the agent would be allowed to propose it."""
    if not a["device_id"] or not a["active"] or a["user_state"]:
        return False
    d = db.device(conn, site, a["device_id"])
    if not d or not d["is_on"]:
        return False
    room = db.latest_room(conn, site, d["room"])
    return policy.check_switch(d, False, policy.AGENT, room).allowed


def listing(conn, site: str, limit: int = 8) -> dict:
    rows = db.rows(conn.execute("SELECT * FROM alerts WHERE site=? ORDER BY id DESC LIMIT ?", (site, limit)))
    items = []
    for a in rows:
        d = db.device(conn, site, a["device_id"]) if a["device_id"] else None
        items.append({
            "id": a["id"], "kind": a["kind"], "level": a["level"], "title": a["title"], "body": a["body"],
            "clock": a["clock"], "active": bool(a["active"]), "user_state": a["user_state"],
            "device_id": a["device_id"], "device_name": d and d["name"],
            "can_act": _can_act(conn, site, a),
        })
    return {"items": items, "last_id": rows[0]["id"] if rows else 0,
            "open": sum(1 for i in items if i["active"] and not i["user_state"])}


# ---------------- the human's answer ----------------

def _get(conn, site: str, alert_id: int) -> dict:
    a = db.one(conn.execute("SELECT * FROM alerts WHERE id=? AND site=?", (alert_id, site)))
    if not a:
        raise actions.ActionError("التنبيه غير موجود.")
    return a


def dismiss(conn, site: str, alert_id: int) -> dict:
    a = _get(conn, site, alert_id)
    conn.execute("UPDATE alerts SET user_state='dismissed' WHERE id=?", (a["id"],))
    return {"ok": True}


def act(conn, site: str, alert_id: int) -> dict:
    """"طفّيه؟" was pressed: create an approval request. Nothing is switched here."""
    a = _get(conn, site, alert_id)
    if not a["device_id"]:
        raise actions.ActionError("لا يرتبط هذا التنبيه بجهاز يمكن إطفاؤه.")
    if actions.flag(conn, "estop", site):
        raise actions.ActionError("الوكيل متوقف (طوارئ).")
    if actions.pending_approval(conn, site):
        raise actions.ActionError("هناك طلب موافقة آخر بانتظار ردّك. ردّ عليه أولًا.")
    d = actions.require_device(conn, site, a["device_id"])
    if not d["is_on"]:
        raise actions.ActionError(f"{d['name']} مطفأ بالفعل.")
    room = db.latest_room(conn, site, d["room"])
    decision = policy.check_switch(d, False, policy.AGENT, room,
                                   safe_mode=actions.flag(conn, "safe_mode", site))
    if not decision.allowed:
        db.audit(conn, site, "T0", "policy", "proposal_blocked",
                 f"لن نقترح إطفاء {d['name']} من التنبيه: {decision.reason_ar}")
        raise actions.ActionError(decision.reason_ar)
    price = billing.marginal_price((db.latest_meter(conn, site) or {}).get("energy_kwh") or 0.0,
                                   config.load_tariff(),
                                   db.get_state(conn, f"tariff_type:{site}", config.load_tariff()["default_type"]))
    details = {"device": d["name"], "signature_w": round(d["signature_w"]),
               "signature_measured": bool(d["signature_measured"]),
               "saving_jod_per_hour": round(d["signature_w"] / 1000 * price, 3),
               "price_jod_per_kwh": price, "from_alert": a["id"], "explained_by": "rules",
               "alternative": "نتركه يعمل، ويبقى التنبيه ظاهرًا."}
    approval_id = actions.request_approval(conn, site, d, False, f"إطفاء {d['name']}؟",
                                           f"{a['title']}: {a['body']}", details)
    conn.execute("UPDATE alerts SET user_state='acted' WHERE id=?", (a["id"],))
    db.audit(conn, site, "T1", "human", "proposal",
             f"من التنبيه: طلب إطفاء {d['name']} (−{round(d['signature_w'])} واط). بانتظار الموافقة.", details)
    return {"approval_id": approval_id}
