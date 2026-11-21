"""Home EV charger: recognise charging sessions, report them, and suggest smart charging.

What it does, every agent tick:
  1. Recognise a charging session from the main meter (NILM-lite): when the charger
     is on and the meter jumps by about the charger's signature (≈ 7.4 kW), the
     session starts. It ends when the car is full (the draw tapers to ~0) or the
     charger is switched off.
  2. Measure the energy of the session: the meter power above what the house drew
     just before the session started, added up over time. This is a MEASURED
     number (from the meter), never a made-up one.
  3. Tell the owner: "charging started" (battery %, time to the target, expected
     kWh and cost) and "charging finished" (kWh drawn, cost, duration).
     The messages go to the phone through backend/alerts.py when that module is
     present, and always to the audit log.
  4. Smart charging: in the evening peak, when the house already draws a lot, the
     agent PROPOSES to pause charging and resume at night. It asks the human
     (Approve / Reject). It never proposes it if the car would then miss the
     owner's "ready by" time (checked in plain code, below).

Honest note on money: Jordan's household tariff in config/tariff.json is tiered by
monthly kWh, with no cheaper night price. So moving charging to the night does not
make the kWh cheaper here; it lowers the evening peak (less risk of overloading the
main breaker) and keeps the house comfortable. If a time-of-use EV tariff is filled
in config (sites.json "ev.night_price_jod_per_kwh"), the saving is computed from it.

The car's battery % comes from the charger (simulated here; real smart wallboxes can
report it). Battery size and the charger power are in config/sites.json ("ev").
"""

import time

from backend import actions, billing, config, db, policy

try:   # phone warnings (added by the warnings feature); without it we only log.
    from backend import alerts
except ImportError:  # pragma: no cover
    alerts = None

EV_KIND = "ev"
STEP_MATCH = 0.35        # a meter step within ±35 % of the signature counts as "the charger"
FULL_SOC = 99.0
PEAK_START_H, PEAK_END_H = 17, 23   # evening peak on the site clock
NIGHT_START = "00:00"


def charger(conn, site: str) -> dict | None:
    return next((d for d in db.devices(conn, site) if d["kind"] == EV_KIND), None)


def ev_config(site: str) -> dict:
    return config.load_sites()[site].get("ev") or {}


def store_reading(conn, site: str, ev: dict | None, meter_ts: float) -> None:
    """Called by ingest: what the charger reports (battery %, plugged in)."""
    if ev is None:
        return
    db.set_state(conn, f"ev:{site}", {"soc_pct": ev.get("soc_pct"), "plugged": bool(ev.get("plugged")),
                                      "ts": meter_ts})


def _price(conn, site: str) -> float:
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    meter = db.latest_meter(conn, site) or {}
    return billing.marginal_price(meter.get("energy_kwh") or 0.0, tariff, ttype)


def _kwh_left_in_tier(conn, site: str) -> float | None:
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    kwh = (db.latest_meter(conn, site) or {}).get("energy_kwh") or 0.0
    for limit, _price_ in tariff["types"][ttype]["tiers"]:
        if limit is not None and kwh < limit:
            return round(limit - kwh, 1)
    return None


def _fmt_h(minutes: float) -> str:
    m = max(0, round(minutes))
    return f"{m // 60} س و {m % 60:02d} د" if m >= 60 else f"{m} دقيقة"


def _clock_h(ts: float) -> float:
    t = time.localtime(ts)
    return t.tm_hour + t.tm_min / 60


def needed_kwh(site: str, soc: float | None) -> float | None:
    cfg = ev_config(site)
    if soc is None or not cfg:
        return None
    return max(0.0, (cfg.get("target_soc", 80) - soc) / 100 * cfg.get("battery_kwh", 60))


def minutes_to_target(site: str, soc: float | None, power_w: float) -> float | None:
    kwh = needed_kwh(site, soc)
    if kwh is None or power_w <= 100:
        return None
    return kwh / (power_w / 1000) * 60


def _notify(conn, site: str, key: str, title: str, body: str, device_id: str, level: str = "info") -> None:
    db.audit(conn, site, "T0", "agent", "ev", f"{title} {body}")
    if alerts is not None:
        try:
            alerts.raise_alert(conn, site, key, "ev_charging", level, title, body, device_id)
            alerts.resolve(conn, site, key)   # a one-off message, not a standing warning
        except Exception as exc:  # never break the agent loop for a notification
            print("ev notify failed:", exc)


# ---------------- the session tracker (called every tick) ----------------

def track(conn, site: str, now: float) -> None:
    d = charger(conn, site)
    if not d:
        return
    meter = db.latest_meter(conn, site)
    if not meter:
        return
    ts = meter["meter_ts"]
    car = db.get_state(conn, f"ev:{site}", {}) or {}
    soc = car.get("soc_pct")
    sess = db.get_state(conn, f"ev_session:{site}")
    power = meter["power_w"]

    if sess is None:
        if not d["is_on"]:
            db.set_state(conn, f"ev_before_w:{site}", power)   # what the house draws without the car
            return
        before = db.get_state(conn, f"ev_before_w:{site}", power)
        step = power - before
        sig = d["signature_w"] or d["rated_w"]
        if abs(step - sig) <= STEP_MATCH * sig:
            sess = {"start_ts": ts, "last_ts": ts, "base_w": before, "kwh": 0.0, "start_soc": soc,
                    "step_w": round(step), "peak_w": round(step)}
            db.set_state(conn, f"ev_session:{site}", sess)
            mins = minutes_to_target(site, soc, step)
            need = needed_kwh(site, soc)
            price = _price(conn, site)
            parts = [f"رصد العدّاد درجة +{step / 1000:.1f} kW تطابق بصمة الشاحن ({sig / 1000:.1f} kW)."]
            if soc is not None:
                parts.append(f"البطارية {soc:.0f}٪.")
            if mins is not None and need is not None:
                parts.append(f"للوصول إلى {ev_config(site).get('target_soc', 80)}٪ تحتاج نحو {_fmt_h(mins)} "
                             f"و {need:.1f} kWh ≈ {need * price:.2f} دينار.")
            left = _kwh_left_in_tier(conn, site)
            if need is not None and left is not None and need > left:
                parts.append(f"تنبيه: بقي {left:.0f} kWh فقط على الشريحة الحالية، وسيُدخلك الشحن إلى الشريحة الأغلى.")
            _notify(conn, site, f"ev_start:{int(ts)}", "🔌 بدأ شحن السيارة.", " ".join(parts), d["id"])
        return

    # A session is running: add up the measured energy above the house's own load.
    dt_h = max(0.0, min(ts - sess["last_ts"], 600)) / 3600
    car_w = max(0.0, power - sess["base_w"])
    sess["kwh"] = round(sess["kwh"] + car_w / 1000 * dt_h, 3)
    sess["last_ts"] = ts
    sess["car_w"] = round(car_w)
    sess["peak_w"] = max(sess.get("peak_w", 0), round(car_w))
    done_full = soc is not None and soc >= FULL_SOC
    tapered = d["is_on"] and car_w < 0.1 * (d["signature_w"] or d["rated_w"]) and ts - sess["start_ts"] > 600
    if not d["is_on"] or done_full or tapered:
        price = _price(conn, site)
        minutes = (ts - sess["start_ts"]) / 60
        if not d["is_on"] and d["agent_off"]:
            why = "أوقفنا الشحن مؤقتًا بموافقتك، وسيُستأنف تلقائيًا ليلًا"
        else:
            why = "انطفأ الشاحن" if not d["is_on"] else "امتلأت البطارية وانخفض السحب إلى الصفر تقريبًا"
        body = (f"{why}. استهلكت {sess['kwh']:.1f} kWh (مقاسة بالعدّاد) ≈ {sess['kwh'] * price:.2f} دينار "
                f"خلال {_fmt_h(minutes)}.")
        if soc is not None:
            body += f" البطارية الآن {soc:.0f}٪."
        title = "⏸ أوقفنا شحن السيارة مؤقتًا." if not d["is_on"] and d["agent_off"] else "✅ اكتمل شحن السيارة."
        _notify(conn, site, f"ev_end:{int(ts)}", title, body, d["id"])
        db.set_state(conn, f"ev_last:{site}", {**sess, "end_ts": ts, "end_soc": soc,
                                               "jod": round(sess["kwh"] * price, 3)})
        db.set_state(conn, f"ev_session:{site}", None)
        return
    db.set_state(conn, f"ev_session:{site}", sess)


# ---------------- smart charging proposal (needs the human's approval) ----------------

def minutes_until(now_ts: float, hhmm: str) -> int:
    t = time.localtime(now_ts)
    target = policy._minutes(hhmm)
    return (target - (t.tm_hour * 60 + t.tm_min)) % 1440 or 1440


def night_plan(site: str, now_ts: float, soc: float | None, power_w: float) -> dict | None:
    """Pause now, resume at 00:00. Only if the car is still ready by the owner's time."""
    cfg = ev_config(site)
    need_min = minutes_to_target(site, soc, power_w)
    if need_min is None:
        return None
    resume_in = minutes_until(now_ts, NIGHT_START)
    ready_by = cfg.get("ready_by", "07:00")
    window = minutes_until(now_ts, ready_by) - resume_in   # minutes between 00:00 and ready_by
    if window <= 0 or need_min > window:
        return None   # pausing would make the car miss the owner's time: never propose it
    return {"resume_in_min": resume_in, "resume_at": NIGHT_START, "ready_by": ready_by,
            "need_min": round(need_min), "window_min": window}


def maybe_propose(conn, site: str, now: float) -> bool:
    """Called by the agent when it is free to ask. Returns True if it asked the human."""
    d = charger(conn, site)
    sess = db.get_state(conn, f"ev_session:{site}")
    if not d or not d["is_on"] or not sess or d["agent_off"]:
        return False
    meter = db.latest_meter(conn, site)
    ts = meter["meter_ts"]
    if not (PEAK_START_H <= _clock_h(ts) < PEAK_END_H):
        return False
    from backend.agent import recently_asked   # local import: agent imports this module
    if recently_asked(conn, site, d["id"], now):
        return False
    limit_w = ev_config(site).get("main_breaker_w", 9200)
    house_w = meter["power_w"]
    if house_w < 0.8 * limit_w:
        return False
    car = db.get_state(conn, f"ev:{site}", {}) or {}
    plan = night_plan(site, ts, car.get("soc_pct"), sess.get("car_w") or d["signature_w"])
    if not plan:
        return False
    decision = policy.check_switch(d, False, policy.AGENT, db.latest_room(conn, site, d["room"]),
                                   estop=actions.flag(conn, "estop", site),
                                   safe_mode=actions.flag(conn, "safe_mode", site))
    if not decision.allowed:
        return False
    cfg = ev_config(site)
    night_price = cfg.get("night_price_jod_per_kwh")
    need = needed_kwh(site, car.get("soc_pct")) or 0
    money = (f"وتوفّر ≈ {need * (_price(conn, site) - night_price):.2f} دينار حسب تعرفة الليل."
             if night_price is not None else
             "التعرفة لدينا بالشرائح لا بالساعة، فالكلفة نفسها، لكننا نخفّف ذروة المساء ونتجنّب فصل القاطع.")
    title = f"تأجيل شحن السيارة إلى {plan['resume_at']}؟"
    near = "فوق" if house_w >= limit_w else "قريب من"
    reason = (f"يستهلك البيت الآن {house_w / 1000:.1f} kW، {near} حد القاطع الرئيسي ({limit_w / 1000:.1f} kW)، والسيارة وحدها {d['signature_w'] / 1000:.1f} kW. "
              + (f"البطارية بلغت الهدف ({cfg.get('target_soc', 80)}٪) أصلًا، فيمكننا الإيقاف الآن والاستئناف الساعة {plan['resume_at']} دون أي مشكلة. "
                 if plan["need_min"] <= 0 else
                 f"إذا أوقفنا الشحن واستأنفناه الساعة {plan['resume_at']}، فستحتاج {_fmt_h(plan['need_min'])} "
                 f"وتكون جاهزة بنسبة {cfg.get('target_soc', 80)}٪ قبل الساعة {plan['ready_by']}. ")
              + money)
    details = {"ev": True, "device": d["name"], "signature_w": round(d["signature_w"]),
               "resume_in_min": plan["resume_in_min"], "resume_at": plan["resume_at"],
               "ready_by": plan["ready_by"], "need_min": plan["need_min"],
               "house_w": round(house_w), "explained_by": "rules",
               "alternative": "نتركها تشحن الآن، ونُطفئ أجهزة أخرى إذا اقتربنا من الحد."}
    actions.request_approval(conn, site, d, False, title, reason, details)
    db.audit(conn, site, "T1", "agent", "proposal",
             f"اقتراح شحن ذكي: إيقاف الشاحن الآن والاستئناف {plan['resume_at']}. بانتظار الموافقة.", details)
    return True


def after_approval(conn, site: str, approval: dict, details: dict) -> None:
    """The human approved a smart-charging pause: set the timer that resumes charging."""
    if not details.get("ev") or not details.get("resume_in_min"):
        return
    from backend import schedules   # local import to avoid a cycle
    try:
        schedules.add_timer(conn, site, approval["device_id"], int(details["resume_in_min"]), True)
        db.set_state(conn, f"ev_resume:{site}", details.get("resume_at"))
    except actions.ActionError as exc:
        db.audit(conn, site, "T0", "policy", "blocked", f"تعذّر ضبط مؤقّت استئناف الشحن: {exc}")


# ---------------- what the pages show ----------------

def status(conn, site: str) -> dict | None:
    d = charger(conn, site)
    if not d:
        return None
    cfg = ev_config(site)
    car = db.get_state(conn, f"ev:{site}", {}) or {}
    sess = db.get_state(conn, f"ev_session:{site}")
    soc = car.get("soc_pct")
    power = (sess or {}).get("car_w") or (d["signature_w"] if d["is_on"] else 0)
    price = _price(conn, site)
    mins = minutes_to_target(site, soc, power) if d["is_on"] and sess else None
    return {
        "device_id": d["id"], "charging": bool(sess) and d["is_on"], "is_on": bool(d["is_on"]),
        "plugged": car.get("plugged", False), "soc_pct": None if soc is None else round(soc, 1),
        "target_soc": cfg.get("target_soc", 80), "battery_kwh": cfg.get("battery_kwh"),
        "ready_by": cfg.get("ready_by"), "power_w": round(power or 0),
        "session_kwh": (sess or {}).get("kwh"), "session_jod": None if not sess else round(sess["kwh"] * price, 3),
        "minutes_to_target": None if mins is None else round(mins),
        "recognized_step_w": (sess or {}).get("step_w"),
        "resume_at": db.get_state(conn, f"ev_resume:{site}") if d["agent_off"] else None,
        "last": db.get_state(conn, f"ev_last:{site}"),
        "kwh_left_in_tier": _kwh_left_in_tier(conn, site),
        "source": cfg.get("source"),
    }
