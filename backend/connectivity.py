"""Is there internet right now? (shown in the UI, used by the offline demo)

WattWise must keep working with NO internet: the meter, the sensors, waste
detection, the approval page and the relays all live on the laptop and the
local Wi-Fi. Only two optional extras need the internet: the weather
(Open-Meteo) and the hosted LLM. When the internet is gone, those two step
aside and the rule-based agent keeps doing everything else.

How we check: every 10 seconds a background thread tries to open one small
web address. Any answer (even an error page) means "online"; no answer within
3 seconds means "offline". The check never blocks the 1-second agent loop.

For rehearsals there is also a switch that pretends the internet is gone
("simulated offline"). It is always labelled as simulated in the UI. In front
of the judges the real test is pulling the router's internet cable.
"""

import os
import threading
import time
import urllib.error
import urllib.request

PROBE_URL = os.environ.get("INTERNET_PROBE_URL", "https://api.open-meteo.com/")
CHECK_EVERY_S = 10
TIMEOUT_S = 3

_lock = threading.Lock()
_checking = threading.Lock()
_state = {
    "online": None,          # None = not checked yet, True / False after the first check
    "forced_offline": False, # the rehearsal switch
    "since": time.time(),    # when the current state (online/offline) started
    "checked_ts": 0.0,
}
_changes: list[dict] = []    # state changes not yet written to the audit log


def probe() -> bool:
    """One real check of the internet. True if any server answered."""
    try:
        with urllib.request.urlopen(PROBE_URL, timeout=TIMEOUT_S):
            return True
    except urllib.error.HTTPError:
        return True          # the server answered (with an error page), so the internet works
    except Exception:
        return False


def is_online() -> bool:
    """What the rest of the code should believe. Unknown (not checked yet) counts as online,
    so the LLM is not blocked during the first seconds after start-up."""
    with _lock:
        if _state["forced_offline"]:
            return False
        return _state["online"] is not False


def _set(online: bool, now: float) -> None:
    with _lock:
        effective_before = None if _state["online"] is None else (
            _state["online"] and not _state["forced_offline"])
        _state["online"] = online
        _state["checked_ts"] = now
        effective = online and not _state["forced_offline"]
        if effective_before is None or effective != effective_before:
            _state["since"] = now
            if effective_before is not None:
                _changes.append({"online": effective, "ts": now, "forced": _state["forced_offline"]})


def set_forced_offline(value: bool, now: float | None = None) -> None:
    """The rehearsal switch: pretend there is no internet (or stop pretending)."""
    now = now or time.time()
    with _lock:
        before = _state["online"] is not False and not _state["forced_offline"]
        _state["forced_offline"] = bool(value)
        after = _state["online"] is not False and not _state["forced_offline"]
        if before != after:
            _state["since"] = now
            _changes.append({"online": after, "ts": now, "forced": bool(value)})


def check_in_background(now: float | None = None) -> None:
    """Called by the agent loop every second; starts a real check at most every 10 s."""
    now = now or time.time()
    if now - _state["checked_ts"] < CHECK_EVERY_S:
        return
    if not _checking.acquire(blocking=False):
        return
    _state["checked_ts"] = now

    def work():
        try:
            _set(probe(), time.time())
        finally:
            _checking.release()

    threading.Thread(target=work, daemon=True, name="internet-check").start()


def pop_changes() -> list[dict]:
    """State changes since the last call (the agent loop writes them to the audit log)."""
    with _lock:
        out = list(_changes)
        _changes.clear()
        return out


def snapshot() -> dict:
    with _lock:
        return dict(_state)


def reset_for_tests(online: bool | None = None) -> None:
    with _lock:
        _state.update(online=online, forced_offline=False, since=time.time(), checked_ts=time.time())
        _changes.clear()


# ---------- what the UI shows ----------

def local_work_since(conn, site: str, since: float) -> dict:
    """What WattWise did by itself, on the laptop, since `since` (counted from the database)."""
    readings = conn.execute("SELECT COUNT(*) FROM meter_readings WHERE site=? AND ts>=?",
                            (site, since)).fetchone()[0]
    events = dict(conn.execute(
        "SELECT event, COUNT(*) FROM audit_log WHERE site=? AND ts>=? GROUP BY event",
        (site, since)).fetchall())
    return {
        "readings": readings,
        "detections": events.get("waste_detected", 0) + events.get("anomaly", 0),
        "approvals": events.get("approved", 0) + events.get("rejected", 0),
        "actions": events.get("approved", 0),
        "verified": events.get("verified", 0),
    }


def status(conn, site: str, now: float | None = None) -> dict:
    now = now or time.time()
    s = snapshot()
    checked = s["online"] is not None or s["forced_offline"]
    online = is_online()
    out = {
        "online": online,
        "checked": checked,
        "forced": s["forced_offline"],
        "since_s": round(now - s["since"]),
        "needs_internet": ["الطقس (Open-Meteo)", "نموذج الذكاء الاصطناعي (اختياري)"],
        "works_offline": ["العدّاد والحسّاسات", "كشف الهدر", "صفحة الموافقة على التلفون",
                          "الريليه (الإطفاء الحقيقي)", "التحقق بالعدّاد", "حساب التوفير"],
    }
    if checked and not online:
        out["local_work"] = local_work_since(conn, site, s["since"])
    return out
