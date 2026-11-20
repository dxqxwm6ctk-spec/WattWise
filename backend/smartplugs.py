"""WiFi smart plugs: the user adds a device by plugging it into a smart plug. No electrician.

How it fits the rest of the system:
- A device on a smart plug is a normal row in `devices`, plus one row in `smart_plugs`.
- The agent, the approvals, the timers and the Policy Guard do not change at all:
  they set `devices.is_on` exactly like for a relay.
- `sync_all()` runs every 2 seconds. It pushes `is_on` to each plug, reads the plug
  back (on/off and watts), and stores the reading.
- Plugs that measure watts give each device its own exact load signature, and the agent
  verifies its actions on the plug itself (not only on the main meter).
- If someone presses the button on the plug, we accept it as a manual change by a human.

All talking to plugs is local (same Wi-Fi), so the demo works with no internet.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor

from backend import config, db, plugs
from backend.actions import AGENT_OFF_NONE, KIND_TIERS, ActionError, require_site
from backend.plugs import PlugError, PlugStatus, simulated
from backend.plugs.base import TYPICAL_W

OFFLINE_AFTER_FAILS = 3        # failed polls in a row before we call a plug offline
OVERLOAD_ALERT = 0.9           # alert above 90% of the plug rating
WARN_ABOVE = 0.8               # ask the user to confirm above 80% of the rating
BIG_LOAD_W = 1500              # any load this big gets a safety warning
SIGNATURE_MIN_W = 3            # below this, the plug is basically idle
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="plug")


# ---------------- safety ----------------

def safety(kind: str, est_w: float, max_w: float) -> dict:
    """Warning shown before adding. level: ok / warn / heater / block."""
    if est_w > max_w:
        return {"level": "block", "needs_confirm": False,
                "message": f"الجهاز ≈ {est_w:.0f} واط، أكبر من حد المقبس ({max_w:.0f} واط). "
                           "لن نضيفه على هذا المقبس: خطر سخونة وحريق."}
    if kind == "heater":
        return {"level": "heater", "needs_confirm": True,
                "message": "السخّان حمل كبير (≈ ٢٠٠٠ واط) ويعمل لساعات. توجد مقابس تتحمّل 16A، "
                           "لكن الأسلم للسخّان كونتاكتور يركّبه كهربائي. إن أردت المتابعة: "
                           "تأكد أن المقبس 16A وموصول بالحائط مباشرة (لا بمشترك)."}
    if est_w >= WARN_ABOVE * max_w or est_w >= BIG_LOAD_W:
        return {"level": "warn", "needs_confirm": True,
                "message": f"حمل مرتفع (≈ {est_w:.0f} واط) قريب من حد المقبس ({max_w:.0f} واط). "
                           "صِله بالحائط مباشرة لا بمشترك، وتأكد أن المقبس لا يسخن."}
    return {"level": "ok", "needs_confirm": False, "message": ""}


def max_w_for(options: dict) -> float:
    try:
        amps = float(options.get("max_a") or plugs.DEFAULT_MAX_A)
    except (TypeError, ValueError):
        amps = plugs.DEFAULT_MAX_A
    return max(1.0, min(amps, 16.0)) * plugs.VOLTS


# ---------------- talking to one plug ----------------

def _clean_options(brand: str, options: dict | None) -> dict:
    allowed = {"gen", "password", "username", "device_id", "local_key", "version", "max_a",
               "dps_switch", "dps_power", "dps_voltage"}
    return {k: str(v).strip() for k, v in (options or {}).items() if k in allowed and v not in (None, "")}


def _driver(brand: str):
    try:
        return plugs.driver(brand)
    except PlugError as exc:
        raise ActionError(str(exc))


def read_plug(brand: str, host: str, options: dict) -> PlugStatus:
    return plugs.driver(brand).status(host, options)


def check(site: str, brand: str, host: str, options: dict | None, kind: str) -> dict:
    """Before adding: can we reach the plug, what does it read, and is it safe for this device?"""
    require_site(site)
    _driver(brand)
    host = (host or "").strip()
    if not host:
        raise ActionError("اكتب عنوان المقبس (IP).")
    options = _clean_options(brand, options)
    if brand == "simulated":   # "plug" a device of this kind into the simulated plug
        try:
            simulated.attach(host, kind)
        except PlugError as exc:
            raise ActionError(str(exc))
    try:
        s = read_plug(brand, host, options)
    except PlugError as exc:
        raise ActionError(str(exc))
    max_w = max_w_for(options)
    measured = s.power_w is not None and s.on and s.power_w > SIGNATURE_MIN_W
    est_w = round(s.power_w) if measured else TYPICAL_W.get(kind, 75)
    return {"on": s.on, "power_w": s.power_w, "meters": s.power_w is not None, "voltage_v": s.voltage_v,
            "est_w": est_w, "measured": measured, "max_w": max_w, "safety": safety(kind, est_w, max_w)}


# ---------------- add / remove ----------------

def add(conn, site: str, brand: str, host: str, options: dict | None, name: str, room: str, kind: str,
        allow: bool, confirm_high_power: bool = False, model: str | None = None) -> dict:
    require_site(site)
    _driver(brand)   # unknown brand -> error
    host = (host or "").strip()
    options = _clean_options(brand, options)
    if not db.one(conn.execute("SELECT 1 AS x FROM rooms WHERE site=? AND id=?", (site, room))):
        raise ActionError("الغرفة غير معروفة.")
    if db.one(conn.execute("SELECT 1 AS x FROM smart_plugs WHERE site=? AND host=?", (site, host))):
        raise ActionError("هذا المقبس مضاف مسبقًا.")
    info = check(site, brand, host, options, kind)
    sf = safety(kind, info["est_w"], info["max_w"])
    if sf["level"] == "block":
        if brand == "simulated":
            simulated.detach(host)
        raise ActionError(sf["message"])
    if sf["needs_confirm"] and not confirm_high_power:
        if brand == "simulated":
            simulated.detach(host)
        raise ActionError("confirm_high_power")

    tier = KIND_TIERS.get(kind, "T1")
    sensitive = kind == "router"
    allow = bool(allow) and tier == "T1" and not sensitive
    device_id = f"plug{int(time.time() * 1000)}"
    name = (name or "").strip()[:60] or kind
    on = int(info["on"])
    conn.execute(
        "INSERT INTO devices (site, id, name, room, kind, rated_w, tier, sensitive, allow, is_on, normal_on, "
        "setpoint, signature_w, signature_measured, added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (site, device_id, name, room, kind, info["est_w"], tier, int(sensitive), int(allow), on, on,
         None, info["est_w"], int(info["measured"]), 1))
    model = (model or "").strip()[:60] or None
    conn.execute(
        "INSERT INTO smart_plugs (site, device_id, brand, host, model, options, meters, max_w, online, power_w, "
        "voltage_v, reported_on, confirmed_on, last_seen_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (site, device_id, brand, host, model, json.dumps(options), int(info["meters"]), info["max_w"], 1,
         info["power_w"], info["voltage_v"], on, on, time.time()))
    access = "T2 محمي (مراقبة فقط)" if tier == "T2" else ("T1 بالقائمة المسموحة" if allow else "تحكم يدوي فقط")
    measured = "مقاسة من المقبس" if info["measured"] else "تقديرية حتى تشغيله"
    db.audit(conn, site, "T0", "human", "plug_added",
             f"مقبس ذكي جديد ({plugs.brand_name(brand)}): {name} · بصمة ≈ {info['est_w']} واط ({measured}) · {access}",
             {"brand": brand, "host": host, "safety": sf["level"]})
    if sf["needs_confirm"]:
        db.audit(conn, site, "T0", "policy", "plug_high_power", "تحذير حمل مرتفع، وأكّد المستخدم أنه فهمه: " + sf["message"])
    return db.device(conn, site, device_id)


def remove(conn, site: str, device_id: str) -> None:
    p = db.plug(conn, site, device_id)
    if not p:
        raise ActionError("هذا الجهاز ليس على مقبس ذكي.")
    d = db.device(conn, site, device_id)
    conn.execute("DELETE FROM smart_plugs WHERE site=? AND device_id=?", (site, device_id))
    conn.execute("DELETE FROM devices WHERE site=? AND id=?", (site, device_id))
    conn.execute("DELETE FROM schedules WHERE site=? AND device_id=?", (site, device_id))
    conn.execute("DELETE FROM timers WHERE site=? AND device_id=?", (site, device_id))
    if p["brand"] == "simulated":
        simulated.detach(p["host"])
    db.audit(conn, site, "T0", "human", "plug_removed", f"أُزيل {d['name'] if d else 'الجهاز'} من المقابس الذكية.")


# ---------------- for the UI and the simulator ----------------

def public(p: dict | None) -> dict | None:
    """What the dashboard and the phone see. Never the options (they can hold a local key)."""
    if not p:
        return None
    return {"brand": p["brand"], "brand_name": plugs.brand_name(p["brand"]), "model": p["model"],
            "host": p["host"], "online": bool(p["online"]), "meters": bool(p["meters"]),
            "power_w": None if p["power_w"] is None else round(p["power_w"], 1),
            "voltage_v": p["voltage_v"], "max_w": round(p["max_w"]), "simulated": p["brand"] == "simulated",
            "error": p["error"]}


def by_device(conn, site: str) -> dict[str, dict]:
    return {p["device_id"]: p for p in db.rows(conn.execute("SELECT * FROM smart_plugs WHERE site=?", (site,)))}


def sim_loads(conn, site: str) -> dict[str, float]:
    """Simulated plugs' real watts, so the simulator adds them to the main meter."""
    rows = db.rows(conn.execute("SELECT device_id, host FROM smart_plugs WHERE site=? AND brand='simulated'",
                                (site,)))
    return {r["device_id"]: simulated.load_w(r["host"]) for r in rows}


def restore_simulated() -> None:
    """At start-up: plug the simulated devices back in (their state lives in memory)."""
    with db.connect() as conn:
        for r in db.rows(conn.execute(
                "SELECT p.host, d.kind, d.is_on FROM smart_plugs p JOIN devices d "
                "ON d.site=p.site AND d.id=p.device_id WHERE p.brand='simulated'")):
            simulated.attach(r["host"], r["kind"], bool(r["is_on"]))


# ---------------- the sync loop ----------------

def _poll(job: dict) -> dict:
    """Network part, no database: push the wanted state if needed, then read the plug."""
    p, want = job["plug"], job["want"]
    options = json.loads(p["options"] or "{}")
    out = {"ok": False, "status": None, "error": None, "manual": False, "switched": False}
    try:
        s = read_plug(p["brand"], p["host"], options)
        if s.on != want:
            if p["confirmed_on"] is not None and bool(p["confirmed_on"]) == want:
                out["manual"] = True       # plug and backend agreed, now the plug changed: a human did it
            else:
                plugs.driver(p["brand"]).switch(p["host"], options, want)
                out["switched"] = True
                s = read_plug(p["brand"], p["host"], options)
        out.update(ok=True, status=s)
    except PlugError as exc:
        out["error"] = str(exc)
    except Exception as exc:   # a driver bug must never stop the loop
        out["error"] = f"خطأ غير متوقع: {type(exc).__name__}"
    return out


def sync_all() -> None:
    with db.connect() as conn:
        jobs = []
        for p in db.rows(conn.execute("SELECT * FROM smart_plugs")):
            d = db.device(conn, p["site"], p["device_id"])
            if d:
                jobs.append({"plug": p, "want": bool(d["is_on"])})
    if not jobs:
        return
    results = list(_pool.map(_poll, jobs, timeout=30))
    with db.connect() as conn:
        for job, res in zip(jobs, results):
            _store(conn, job, res)


def _store(conn, job: dict, res: dict) -> None:
    p, want = job["plug"], job["want"]
    site, dev_id = p["site"], p["device_id"]
    d = db.device(conn, site, dev_id)
    if not d:
        return
    now = time.time()
    if not res["ok"]:
        fails = (p["fails"] or 0) + 1
        online = int(fails < OFFLINE_AFTER_FAILS)
        conn.execute("UPDATE smart_plugs SET fails=?, online=?, error=? WHERE site=? AND device_id=?",
                     (fails, online, res["error"], site, dev_id))
        if p["online"] and not online:
            db.audit(conn, site, "T0", "system", "plug_offline",
                     f"انقطع المقبس الذكي الخاص بـ{d['name']}: {res['error']} لن نتحكّم به حتى يعود.")
        return

    s: PlugStatus = res["status"]
    if not p["online"]:
        db.audit(conn, site, "T0", "system", "plug_online", f"عاد اتصال المقبس الذكي الخاص بـ{d['name']}.")
    still_same_wish = bool(d["is_on"]) == want
    confirmed = p["confirmed_on"]
    if s.on == bool(d["is_on"]):
        confirmed = int(s.on)
    elif res["manual"] and still_same_wish:
        # Someone pressed the plug's own button: accept it as a human action.
        db.set_device(conn, site, dev_id, is_on=int(s.on), agent_off=AGENT_OFF_NONE)
        confirmed = int(s.on)
        db.audit(conn, site, "MANUAL", "human", "plug_button",
                 f"{'تشغيل' if s.on else 'إطفاء'} {d['name']} من زر المقبس نفسه.")

    overload = p["overload"]
    if s.power_w is not None and p["max_w"]:
        if s.power_w > OVERLOAD_ALERT * p["max_w"] and not overload:
            overload = 1
            db.audit(conn, site, "T0", "policy", "plug_overload",
                     f"تنبيه: {d['name']} يستهلك {s.power_w:.0f} واط، قريبًا من حد المقبس ({p['max_w']:.0f} واط). "
                     "تأكد أن المقبس لا يسخن.")
        elif s.power_w < 0.8 * p["max_w"]:
            overload = 0

    conn.execute(
        "UPDATE smart_plugs SET online=1, fails=0, error=NULL, power_w=?, energy_kwh=?, voltage_v=?, "
        "reported_on=?, confirmed_on=?, last_seen_ts=?, overload=? WHERE site=? AND device_id=?",
        (s.power_w, s.energy_kwh, s.voltage_v, int(s.on), confirmed, now, overload, site, dev_id))

    # Fingerprinting: a metering plug tells us the device's exact signature.
    if s.on and s.power_w is not None and s.power_w > SIGNATURE_MIN_W and d["is_on"]:
        old = d["signature_w"] if d["signature_measured"] else s.power_w
        db.set_device(conn, site, dev_id, signature_w=round(0.8 * old + 0.2 * s.power_w, 1), signature_measured=1)


def poll_interval() -> float:
    return config.PLUG_POLL_S
