"""NILM-lite on one meter: find step changes, recognise saved fingerprints, flag unknown devices.

The idea in one sentence: when a device switches on, the meter jumps up by
that device's watts, and when it switches off the meter drops by the same
amount. So every clean jump ("step") is one device.

For each meter stream we keep the last 6 readings (1 per second):
    before = readings 1..3, after = readings 4..6
If both groups are steady and their medians differ by more than a threshold,
that difference is a step (delta watts). With the power factor (pf) from the
PZEM we also get the reactive power, so each step has two numbers:
    watts and pf   -> the device's "fingerprint"
A laptop charger (about 60 W, pf about 0.55) and a fan (about 55 W, pf about
0.85) draw similar watts but have a different pf, so pf helps tell them apart.

Streams:
  "main"            the main meter (whole site). On the simulator it is noisy
                    (about +-20 W), so only big steps are visible.
  "circuit:<room>"  the PZEM clamped on ONE room's breaker (teach mode). Small
                    devices (a few watts) are visible there.
On the real lab site there is one room, so the main meter IS the room circuit.

What happens with a step:
  1. a known relay device was just switched (or its set point changed) -> known, nothing to do
  2. it matches the fridge's compressor cycling -> known
  3. it matches a fingerprint the user saved -> "recognised: laptop on"
  4. teach mode is listening on this room -> it becomes a candidate (backend/teach.py)
  5. otherwise, a step UP is an unknown device -> alert + ask the user what it is

Nothing here switches anything. Alerts are tier 0 (messages only).
"""

import math
import time
from statistics import mean

from backend import config, db

WINDOW = 3                 # readings per group (before / after)
GAP_RESET_S = 5            # readings missing longer than this: start the buffer again
CHANGE_WINDOW_S = 12       # a step this soon after a known device changed is explained by it
NOISY_TOL_W, NOISY_MIN_STEP_W = 45.0, 40.0   # simulator main meter (noise about +-20 W)
UNKNOWN_DEDUP_S = 120      # do not alert twice for the same unknown device
NOISY_UNKNOWN_MIN_W = 100  # on the noisy main meter only big unknown devices are reported

# What a step of this size and power factor usually is. Typical values from
# appliance nameplates and common measurements; a guess only, the user confirms.
# (kind, Arabic label, watts min, watts max, pf min, pf max)
GUESSES = [
    ("light", "ضو LED صغير", 2, 15, 0.45, 0.95),
    ("other", "شاحن تلفون أو راوتر", 2, 15, 0.3, 0.6),
    ("light", "ضو LED كبير", 15, 60, 0.9, 0.97),
    ("light", "لمبة عادية (توهّج أو هالوجين)", 25, 150, 0.97, 1.0),
    ("pc", "لابتوب (الشاحن)", 30, 100, 0.45, 0.75),
    ("fan", "مروحة", 25, 90, 0.75, 0.9),
    ("tv", "تلفزيون أو شاشة", 60, 250, 0.9, 1.0),
    ("pc", "كمبيوتر مكتبي", 100, 350, 0.88, 1.0),
    ("fridge", "ثلاجة", 80, 250, 0.6, 0.85),
    ("washer", "غسالة", 300, 900, 0.6, 0.9),
    ("ac", "مكيّف", 700, 2500, 0.8, 0.96),
    ("heater", "سخّان أو غلّاية أو مكوى", 600, 3000, 0.97, 1.0),
]

# In-memory buffers per (site, stream): list of (ts, watts, var). Lost on restart, that is fine.
_buffers: dict[tuple[str, str], list[tuple[float, float, float | None]]] = {}


# ---------------- pure helpers (easy to test) ----------------

def reactive(power_w: float, pf: float | None) -> float | None:
    """Reactive power (var) from watts and power factor. None without a usable pf."""
    if pf is None or not 0 < pf <= 1:
        return None
    return power_w * math.tan(math.acos(pf))


def step_pf(dp: float, dq: float | None) -> float | None:
    """Power factor of the device that caused the step."""
    if dq is None or dp == 0:
        return None
    return round(abs(dp) / math.hypot(dp, dq), 2)


def _limits(level: float, precise: bool) -> tuple[float, float]:
    """(allowed wobble inside a steady group, smallest step we report) in watts."""
    if precise:
        tol = 1.5 + 0.005 * level         # PZEM: 0.1 W resolution, about 0.5 % accuracy
        return tol, max(4.0, 2 * tol)
    return NOISY_TOL_W, NOISY_MIN_STEP_W


def _steady(win: list[tuple[float, float, float | None]], precise: bool) -> bool:
    p = [x[1] for x in win]
    return max(p) - min(p) <= _limits(max(p), precise)[0]


def _level(win: list[tuple[float, float, float | None]]) -> tuple[float, float | None]:
    q = [x[2] for x in win]
    return mean(x[1] for x in win), (mean(q) if all(v is not None for v in q) else None)


def compare(before: tuple[float, float | None], win: list[tuple[float, float, float | None]],
            precise: bool) -> dict | None:
    """A steady group of readings against the last steady level. Returns the step or None."""
    p0, q0 = before
    p1, q1 = _level(win)
    dp = p1 - p0
    if abs(dp) < _limits(max(p0, p1), precise)[1]:
        return None
    dq = q1 - q0 if q0 is not None and q1 is not None else None
    pf = step_pf(dp, dq)
    if pf is None:
        pf_note = "none"
    elif abs(dp) < 15 or not precise:
        pf_note = "weak"                  # pf has 2 decimals: on a tiny step or a big total it is not reliable
    else:
        pf_note = "ok"
    return {"dp": round(dp, 1), "pf": pf, "pf_quality": pf_note,
            "before_w": round(p0, 1), "after_w": round(p1, 1), "noisy": not precise}


def detect_step(buf: list[tuple[float, float, float | None]], precise: bool) -> dict | None:
    """Look at the last 6 readings: 3 steady before, 3 steady after. Returns the step or None."""
    if len(buf) < 2 * WINDOW:
        return None
    a, b = buf[-2 * WINDOW:-WINDOW], buf[-WINDOW:]
    if not (_steady(a, precise) and _steady(b, precise)):
        return None                       # still changing (or a ramp), not a clean step
    return compare(_level(a), b, precise)


# Last steady level per stream, so two devices switching 1-2 seconds apart still give one
# (combined) step instead of being missed.
_levels: dict[tuple[str, str], tuple[float, float | None]] = {}


def feed(site: str, stream: str, ts: float, power_w: float, var: float | None, precise: bool) -> dict | None:
    """Add one reading to a stream. Returns a step when one is complete."""
    key = (site, stream)
    buf = _buffers.setdefault(key, [])
    if buf and ts - buf[-1][0] > GAP_RESET_S:
        buf.clear()
        _levels.pop(key, None)
    buf.append((ts, power_w, var))
    del buf[:-WINDOW]
    if len(buf) < WINDOW or not _steady(buf, precise):
        return None
    before = _levels.get(key)
    _levels[key] = _level(buf)
    return compare(before, buf, precise) if before else None


def reset_buffers(site: str | None = None) -> None:
    for d in (_buffers, _levels):
        for key in list(d):
            if site is None or key[0] == site:
                del d[key]


def guess(watts: float, pf: float | None, pf_quality: str = "ok") -> list[dict]:
    """Best two guesses for a device from its watts and pf. Confidence is rough, 0..1."""
    w = abs(watts)
    pf_weight = 0.0 if pf is None or pf_quality == "none" else (0.4 if pf_quality == "weak" else 1.0)
    scored = []
    for kind, label, wmin, wmax, pmin, pmax in GUESSES:
        # 1.0 inside the range, falling off outside (relative distance).
        sw = 1.0 if wmin <= w <= wmax else max(0.0, 1 - min(abs(w - wmin), abs(w - wmax)) / max(wmin, 1))
        if pf_weight and pf is not None:
            sp = 1.0 if pmin <= pf <= pmax else max(0.0, 1 - min(abs(pf - pmin), abs(pf - pmax)) / 0.15)
            score = sw * (1 - pf_weight + pf_weight * sp)
        else:
            score = sw * 0.6              # watts only: never very sure
        if score > 0:
            scored.append({"kind": kind, "label": label, "confidence": round(score, 2)})
    scored.sort(key=lambda g: -g["confidence"])
    return scored[:2] or [{"kind": "other", "label": "جهاز", "confidence": 0.1}]


def matches(watts: float, pf: float | None, fp_w: float, fp_pf: float | None, noisy: bool = False) -> bool:
    """Does a step look like a saved fingerprint? Watts within 15 % (or 3 W) and pf within 0.1.

    On the noisy main meter (simulator, +-20 W) we allow 25 W and ignore pf.
    """
    w = abs(watts)
    if abs(w - fp_w) > max(3.0, 0.15 * fp_w, 25.0 if noisy else 0.0):
        return False
    if pf is None or fp_pf is None or w < 15 or noisy:
        return True
    return abs(pf - fp_pf) <= 0.1


# ---------------- storage ----------------

def fingerprints(conn, site: str, room: str | None = None) -> list[dict]:
    if room:
        return db.rows(conn.execute("SELECT * FROM fingerprints WHERE site=? AND room=? ORDER BY id", (site, room)))
    return db.rows(conn.execute("SELECT * FROM fingerprints WHERE site=? ORDER BY id", (site,)))


def save_fingerprint(conn, site: str, room: str, name: str, kind: str, watts: float, pf: float | None,
                     samples: int = 1, source: str = "teach") -> int:
    cur = conn.execute(
        "INSERT INTO fingerprints (site, room, name, kind, watts, pf, samples, created_ts, source) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (site, room, name, kind, round(abs(watts), 1), pf, samples, time.time(), source))
    return cur.lastrowid


def delete_fingerprint(conn, site: str, fp_id: int) -> None:
    conn.execute("DELETE FROM fingerprints WHERE site=? AND id=?", (site, fp_id))
    on = db.get_state(conn, f"nilm_on:{site}") or {}
    on.pop(str(fp_id), None)
    db.set_state(conn, f"nilm_on:{site}", on)


def room_name(conn, site: str, room_id: str | None) -> str:
    if not room_id:
        return "غرفة مش معروفة"
    r = db.one(conn.execute("SELECT name FROM rooms WHERE site=? AND id=?", (site, room_id)))
    return r["name"] if r else room_id


# ---------------- the live part (called for every reading) ----------------

def _track_device_changes(conn, site: str, now: float) -> list[dict]:
    """Remember when a known device was switched or its set point changed (by anyone)."""
    snap = db.get_state(conn, f"nilm_snap:{site}") or {}
    old = db.get_state(conn, f"nilm_changes:{site}") or []
    changes = [c for c in old if now - c["ts"] < CHANGE_WINDOW_S]
    new_snap, changed = {}, False
    for d in db.devices(conn, site):
        key = [d["is_on"], d["setpoint"]]
        new_snap[d["id"]] = key
        if d["id"] in snap and snap[d["id"]] != key:
            changes.append({"ts": now, "device_id": d["id"], "room": d["room"]})
            changed = True
    if new_snap != snap:
        db.set_state(conn, f"nilm_snap:{site}", new_snap)
    if changed or len(changes) != len(old):
        db.set_state(conn, f"nilm_changes:{site}", changes)
    return changes


def observe(conn, site: str, payload: dict, now: float | None = None) -> None:
    """Feed the main meter (and the room circuit, if any) into the step detector."""
    from backend import teach   # teach imports nilm

    now = now or time.time()
    cfg = config.load_sites()[site]
    room_ids = [r["id"] for r in cfg["rooms"]]
    single_room = room_ids[0] if len(room_ids) == 1 else None
    t = teach.session(conn, site)
    if t and cfg["source"] != "simulator":
        single_room = t["room"]           # real hardware: the PZEM was moved to this room's breaker
    changes = _track_device_changes(conn, site, now)
    meter = payload["meter"]

    streams = []
    p = float(meter["power_w"])
    streams.append(("main", single_room, p, reactive(p, meter.get("pf")), cfg["source"] != "simulator"))
    c = payload.get("circuit")
    if c and c.get("room_id") in room_ids:
        cp = float(c["power_w"])
        streams.append((f"circuit:{c['room_id']}", c["room_id"], cp, reactive(cp, c.get("pf")), True))

    for stream, room, pw, var, precise in streams:
        ev = feed(site, stream, now, pw, var, precise)
        if ev:
            ev.update(stream=stream, room=room, ts=now)
            _handle(conn, site, ev, changes, now)

    teach.check(conn, site, now)
    _recognised_waste(conn, site, now)


def _handle(conn, site: str, ev: dict, changes: list[dict], now: float) -> None:
    from backend import teach

    if db.get_state(conn, f"learn:{site}"):
        return                            # the "add device" flow is measuring its own step
    room = ev["room"]
    on_circuit = ev["stream"].startswith("circuit:")

    # 1. A known device was just switched: the step is that device.
    if any(c["room"] == room for c in changes) if on_circuit else changes:
        return

    # 2. The fridge compressor cycles on and off by itself. If another device switched in the
    #    same second, the step is (fridge on/off) + (that device): keep only the device's part.
    if _fridge_explains(conn, site, ev):
        return

    # On the noisy main meter a 60 W laptop and a 60 W stranger look the same (and pf is not
    # reliable on a big total), so small devices are only judged on a room's breaker.
    if ev["noisy"]:
        t = teach.session(conn, site)
        if ev["dp"] >= NOISY_UNKNOWN_MIN_W and not (t and t.get("status") == "listening"):
            _unknown_on(conn, site, ev, now)
        elif ev["dp"] <= -NOISY_UNKNOWN_MIN_W:
            _unknown_off(conn, site, ev, now)
        return

    # 3. A fingerprint the user saved.
    fps = [f for f in fingerprints(conn, site) if room is None or f["room"] == room]
    on = db.get_state(conn, f"nilm_on:{site}") or {}
    best = None
    for f in fps:
        # A device that is already on cannot switch on again (and an off one cannot switch off).
        if (str(f["id"]) in on) == (ev["dp"] > 0):
            continue
        if matches(ev["dp"], ev["pf"], f["watts"], f["pf"], ev["noisy"]):
            if best is None or abs(abs(ev["dp"]) - f["watts"]) < abs(abs(ev["dp"]) - best["watts"]):
                best = f
    if best:
        if ev["dp"] > 0 and str(best["id"]) not in on:
            on[str(best["id"])] = {"since": now, "tipped": False}
            db.audit(conn, site, "T0", "agent", "recognised",
                     f"تعرّفت عالبصمة: انشغل {best['name']} ({room_name(conn, site, best['room'])}) ≈ {round(abs(ev['dp']))} واط.",
                     {"step_w": ev["dp"], "pf": ev["pf"], "fingerprint_id": best["id"]})
            teach.note_recognised(conn, site, best, ev)
        elif ev["dp"] < 0 and str(best["id"]) in on:
            on.pop(str(best["id"]))
            db.audit(conn, site, "T0", "agent", "recognised_off",
                     f"تعرّفت عالبصمة: انطفى {best['name']} ({room_name(conn, site, best['room'])}).",
                     {"step_w": ev["dp"], "fingerprint_id": best["id"]})
        db.set_state(conn, f"nilm_on:{site}", on)
        return

    # 4. Teach mode: the user is switching devices on one by one in this room.
    t = teach.session(conn, site)
    if t and t.get("status") == "listening":
        if room == t["room"]:
            if ev["dp"] > 0:
                teach.add_candidate(conn, site, ev)
            return
        if ev["stream"] == "main":
            return                        # the teach room's devices also show on the main meter

    # 5. Unknown device.
    if ev["dp"] > 0:
        _unknown_on(conn, site, ev, now)
    else:
        _unknown_off(conn, site, ev, now)


def _fridge_explains(conn, site: str, ev: dict) -> bool:
    """True when the step is just the fridge. May shrink ev["dp"] to the part that is not the fridge."""
    running = db.get_state(conn, f"nilm_fridge:{site}") or {}
    small = NOISY_MIN_STEP_W if ev["noisy"] else 4.0
    for d in db.devices(conn, site):
        if d["kind"] != "fridge" or not d["is_on"] or (ev["room"] is not None and d["room"] != ev["room"]):
            continue
        key = f"{ev['stream']}|{d['id']}"   # each meter stream sees the same fridge step once
        sig, state = d["signature_w"], running.get(key)
        tol = NOISY_MIN_STEP_W if ev["noisy"] else max(4.0, 0.06 * sig)
        for o in (sig, -sig):
            if abs(ev["dp"] - o) <= tol:  # just the fridge (this also corrects a stale state)
                running[key] = o > 0
                db.set_state(conn, f"nilm_fridge:{site}", running)
                return True
        # Fridge + another device: if we know the compressor is running, it can only stop
        # (and the other way round).
        options = [-sig] if state is True else [sig] if state is False else [sig, -sig]
        best = min(options, key=lambda o: abs(ev["dp"] - o))
        rest = ev["dp"] - best
        if abs(rest) < abs(ev["dp"]) and abs(rest) >= small:
            running[key] = best > 0
            db.set_state(conn, f"nilm_fridge:{site}", running)
            ev.update(dp=round(rest, 1), pf=None, pf_quality="none")
            return False
    return False


def unknowns(conn, site: str) -> list[dict]:
    return db.get_state(conn, f"nilm_unknown:{site}") or []


def _unknown_on(conn, site: str, ev: dict, now: float) -> None:
    from backend import teach

    items = unknowns(conn, site)
    for u in items:
        if u["status"] == "open" and now - u["ts"] < UNKNOWN_DEDUP_S and matches(ev["dp"], ev["pf"], u["watts"], u["pf"], ev["noisy"]):
            return
    g = guess(ev["dp"], ev["pf"], ev["pf_quality"])
    pf = ev["pf"] if ev["pf_quality"] == "ok" else None
    u = {"id": int(now * 1000), "ts": now, "watts": round(ev["dp"]), "pf": pf, "room": ev["room"],
         "stream": ev["stream"], "guess": g, "status": "open"}
    items = [x for x in items if x["status"] == "open" or now - x["ts"] < 3600][-20:] + [u]
    db.set_state(conn, f"nilm_unknown:{site}", items)
    where = f"ب{room_name(conn, site, ev['room'])}" if ev["room"] else "(العدّاد الرئيسي، الغرفة مش معروفة)"
    pf_txt = f"، معامل القدرة ≈ {pf}" if pf is not None else ""
    db.audit(conn, site, "T0", "agent", "unknown_device",
             f"في جهاز مجهول بيسحب ≈ {round(ev['dp'])} واط {where}{pf_txt}. ما إله بصمة محفوظة. غالبًا: {g[0]['label']}.",
             {"step_w": ev["dp"], "pf": ev["pf"], "room": ev["room"], "guess": g})
    teach.ask_about_unknown(conn, site, u)


def _unknown_off(conn, site: str, ev: dict, now: float) -> None:
    items = unknowns(conn, site)
    for u in reversed(items):
        if u["status"] == "open" and matches(ev["dp"], ev["pf"], u["watts"], u["pf"], ev["noisy"]):
            u["status"] = "gone"
            db.set_state(conn, f"nilm_unknown:{site}", items)
            db.audit(conn, site, "T0", "agent", "unknown_gone",
                     f"الجهاز المجهول (≈ {u['watts']} واط) انطفى.", {"step_w": ev["dp"]})
            return


def set_unknown_status(conn, site: str, unknown_id: int, status: str) -> None:
    items = unknowns(conn, site)
    for u in items:
        if u["id"] == unknown_id:
            u["status"] = status
    db.set_state(conn, f"nilm_unknown:{site}", items)


def _recognised_waste(conn, site: str, now: float) -> None:
    """A recognised device (no relay on it) runs in an empty room: tell the human once. Tier 0."""
    on = db.get_state(conn, f"nilm_on:{site}") or {}
    if not on:
        return
    from backend import agent, teach

    changed = False
    for fid, info in on.items():
        if info.get("tipped"):
            continue
        f = db.one(conn.execute("SELECT * FROM fingerprints WHERE site=? AND id=?", (site, int(fid))))
        if not f or f["kind"] in config.FORBIDDEN_KINDS:
            continue
        empty_s = agent.empty_for_seconds(conn, site, f["room"], now)
        if empty_s is None or empty_s < max(config.WASTE_EMPTY_S, 30):
            continue
        info["tipped"] = changed = True
        msg = (f"{f['name']} شغّال ب{room_name(conn, site, f['room'])} والغرفة فاضية. "
               f"ما عليه ريليه، فما بقدر أطفيه أنا. إذا بدك طفّيه بإيدك (≈ {round(f['watts'])} واط).")
        db.audit(conn, site, "T0", "agent", "recognised_waste", msg, {"fingerprint_id": f["id"]})
        teach.say_ai(conn, site, msg)
    if changed:
        db.set_state(conn, f"nilm_on:{site}", on)


def status(conn, site: str) -> dict:
    """For the UI."""
    on = db.get_state(conn, f"nilm_on:{site}") or {}
    fps = fingerprints(conn, site)
    return {
        "fingerprints": [{**f, "room_name": room_name(conn, site, f["room"]), "is_on": str(f["id"]) in on}
                         for f in fps],
        "unknown": [u for u in unknowns(conn, site) if u["status"] == "open"],
    }


def clear(conn, site: str) -> None:
    """Demo reset: forget live state (open alerts, who is on). Saved fingerprints stay."""
    for key in ("nilm_unknown", "nilm_on", "nilm_changes", "nilm_fridge"):
        db.set_state(conn, f"{key}:{site}", None)
    reset_buffers(site)
