"""Builds the one JSON object the dashboard and the phone app render."""

import calendar
import json
import time

from backend import (actions, alerts, anomaly, billing, config, connectivity, db, ev, forecast, impact, llm,
                     mv, nilm, schedules, smartplugs, teach, weather)

CATEGORY = {"ac": "المكيّفات", "fan": "المكيّفات", "fridge": "الثلاجة", "heater": "سخّان الماء", "ev": "شحن السيارة",
            "light": "الإنارة"}


def _plan(conn, site, goal):
    plan = db.get_state(conn, f"plan:{site}", None)
    if not goal or not plan or plan.get("goal_id") != goal["id"]:
        return None
    from backend.assistant import step_tag
    steps = plan.get("steps", [])
    return {"by": plan.get("by", "rules"), "steps": steps, "tags": [step_tag(s) for s in steps],
            "summary": plan.get("summary", "")}


def _history(conn, site: str, points: int = 60) -> list[dict]:
    rows = db.rows(conn.execute(
        "SELECT meter_ts, power_w, baseline_w FROM meter_readings WHERE site=? ORDER BY id DESC LIMIT ?",
        (site, points)))
    rows.reverse()
    return [{"t": time.strftime("%H:%M", time.localtime(r["meter_ts"])),
             "power_w": round(r["power_w"], 1), "baseline_w": round(r["baseline_w"], 1)} for r in rows]


def build(conn, site: str) -> dict:
    actions.require_site(site)
    site_cfg = config.load_sites()[site]
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    now = time.time()

    meter = db.latest_meter(conn, site) or {}
    devs = db.devices(conn, site)
    room_rows = db.rooms(conn, site)
    room_names = {r["id"]: r["name"] for r in room_rows}

    plug_rows = smartplugs.by_device(conn, site)
    devices = []
    for d in devs:
        pr = plug_rows.get(d["id"])
        live = pr["power_w"] if pr and pr["meters"] and pr["online"] and pr["power_w"] is not None else None
        devices.append({
            "id": d["id"], "name": d["name"], "room": d["room"], "room_name": room_names.get(d["room"], d["room"]),
            "kind": d["kind"], "tier": "T2" if d["tier"] == "T2" or d["kind"] in config.FORBIDDEN_KINDS else "T1",
            "sensitive": bool(d["sensitive"]), "allow": bool(d["allow"]), "is_on": bool(d["is_on"]),
            "setpoint": d["setpoint"], "est_w": (round(live) if live is not None else round(d["signature_w"])) if d["is_on"] else 0,
            "signature_w": round(d["signature_w"]), "signature_measured": bool(d["signature_measured"]),
            "signature_pf": d["signature_pf"], "load_type": nilm.load_type_ar(d["signature_pf"]),
            "added": bool(d["added"]), "agent_off": d["agent_off"],
            "plug": smartplugs.public(plug_rows.get(d["id"])),
        })

    pending = actions.pending_approval(conn, site)
    waste_rooms = set()
    if pending:
        pd = db.device(conn, site, pending["device_id"])
        if pd:
            waste_rooms.add(pd["room"])

    rooms = []
    for r in room_rows:
        rr = db.latest_room(conn, site, r["id"]) or {}
        rooms.append({
            "id": r["id"], "name": r["name"],
            "power_w": sum(d["est_w"] for d in devices if d["room"] == r["id"]),
            "occupied": None if rr.get("occupied") is None else bool(rr["occupied"]),
            "temp_c": rr.get("temp_c"), "light": rr.get("light"),
            "window_open": None if rr.get("window_open") is None else bool(rr["window_open"]),
            "waste": r["id"] in waste_rooms or actions.get_phase(conn, site) == "analyzing" and any(
                d["room"] == r["id"] and d["is_on"] and rr.get("occupied") == 0 and d["tier"] == "T1"
                and d["allow"] for d in devices),
        })

    # --- bill ---
    kwh_now = meter.get("energy_kwh") or 0.0
    t = time.localtime(meter.get("meter_ts") or now)
    days_in_month = calendar.monthrange(t.tm_year, t.tm_mon)[1]
    elapsed_days = max(0.5, t.tm_mday - 1 + (t.tm_hour + t.tm_min / 60) / 24)
    saved_wh = db.get_state(conn, f"saved_wh:{site}", 0.0)
    projected_kwh = kwh_now / elapsed_days * days_in_month
    goal = actions.active_goal(conn, site)
    tinfo = billing.tier_info(kwh_now, projected_kwh, tariff, ttype)
    price = billing.marginal_price(kwh_now, tariff, ttype)
    bill_now = billing.bill_for(kwh_now, tariff, ttype)

    # Where does the money go? From NILM-lite attribution of measured energy.
    by_cat: dict[str, float] = {}
    for d in devs:
        cat = CATEGORY.get(d["kind"], "غيره")
        by_cat[cat] = by_cat.get(cat, 0.0) + d["energy_wh"]
    total_wh = sum(by_cat.values())
    breakdown = []
    if total_wh > 0:
        top = max(by_cat.values())
        for name, wh in sorted(by_cat.items(), key=lambda x: -x[1]):
            breakdown.append({"name": name, "jod": round(bill_now * wh / total_wh, 2),
                              "pct": round(wh / top * 100)})

    pending_out = None
    if pending:
        pending_out = {
            "id": pending["id"], "title": pending["title"], "reason": pending["reason"],
            "device_id": pending["device_id"], "turn_on": bool(pending["turn_on"]),
            "details": json.loads(pending["details"] or "{}"),
            "expires_in_s": max(0, round(pending["expires_ts"] - now)),
            "timeout_s": config.APPROVAL_TIMEOUT_S,
        }

    last = db.one(conn.execute(
        "SELECT a.status, a.title, d.name AS device_name FROM approvals a LEFT JOIN devices d "
        "ON d.site=a.site AND d.id=a.device_id WHERE a.site=? AND a.status!='pending' ORDER BY a.id DESC LIMIT 1",
        (site,)))

    log = db.rows(conn.execute(
        "SELECT clock, tier, message FROM audit_log WHERE site=? ORDER BY id DESC LIMIT 8", (site,)))

    return {
        "site": site, "site_name": site_cfg["name"], "source": site_cfg["source"],
        "labels": site_cfg.get("labels", {}),
        "demo_label": (site_cfg.get("demo_waste") or {}).get("label"),
        "clock": time.strftime("%H:%M", t),
        "online": bool(meter) and now - meter.get("ts", 0) <= config.STALE_READING_S,
        "meter": {k: meter.get(k) for k in ("power_w", "voltage_v", "current_a", "freq_hz", "energy_kwh", "pf")},
        "history": _history(conn, site),
        "rooms": rooms,
        "devices": devices,
        "agent": {
            "phase": actions.get_phase(conn, site),
            "estop": actions.flag(conn, "estop", site),
            "safe_mode": actions.flag(conn, "safe_mode", site),
            "fault": actions.flag(conn, "fault", site),
            "brain": llm.status(conn),
        },
        "plan": _plan(conn, site, goal),
        "anomaly": anomaly.status(conn, site),
        "alerts": alerts.listing(conn, site),
        "forecast": forecast.cached(conn, site),
        "mv": {k: v for k, v in mv.cached(conn, site).items() if k != "series"},
        "weather": weather.cached(),
        "goal": goal and {"text": goal["text"], "bill_target_jd": goal["bill_target_jd"]},
        "steps": actions.GOAL_STEPS,
        "pending": pending_out,
        "last_approval": last,
        "bill": {
            "type": ttype,
            "types": [{"key": k, "label": v["label"]} for k, v in tariff["types"].items()],
            "who": tariff["types"][ttype]["who"],
            "kwh_now": round(kwh_now, 1), "bill_now": round(bill_now, 2),
            "projected_kwh": round(projected_kwh, 1),
            "bill_projected": round(billing.bill_for(projected_kwh, tariff, ttype), 2),
            "price_jod_per_kwh": price,
            "segments": tinfo["segments"], "message": tinfo["message"],
            "now_pos": round(min(99, kwh_now / tinfo["display_max_kwh"] * 100), 1),
            "proj_pos": round(min(99, projected_kwh / tinfo["display_max_kwh"] * 100), 1),
            "source": tariff.get("price_source"),
        },
        "savings": impact.savings(
            saved_wh,
            impact.today_wh(db.get_state(conn, f"saved_day:{site}", None), meter.get("meter_ts") or now),
            sum(d["signature_w"] for d in devs if d["agent_off"] == actions.AGENT_OFF_VERIFIED),
            price, tariff),
        "internet": connectivity.status(conn, site, now),
        "breakdown": breakdown,
        "log": log,
        "learn": db.get_state(conn, f"learn:{site}"),
        "comfort": {"min_c": config.COMFORT_MIN_TEMP_C, "max_c": config.COMFORT_MAX_TEMP_C},
        "automation": schedules.listing(conn, site),
        "ev": ev.status(conn, site),
        # Teach mode chat, saved device fingerprints and unknown-device alerts.
        "teach": teach.state(conn, site),
    }
