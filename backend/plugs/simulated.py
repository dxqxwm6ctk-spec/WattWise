"""Simulated smart plugs: let us demo "add a smart plug" with no hardware (synthetic data).

They behave like real metering plugs: they answer the scan, switch on/off, and report
watts. The watts come from a typical value for the device type (with a little noise),
and on a simulator site the simulator adds them to the main meter too, so the agent
can verify its actions exactly like with a real plug. Always labelled "simulated" in the UI.
"""

import random
import threading

from backend.plugs.base import TYPICAL_W, PlugError, PlugStatus

BRAND = "simulated"

# What the "scan" finds on the simulated network.
CATALOG = [
    {"host": "sim-shelly-1", "model": "Shelly Plus Plug S (محاكى)", "meters": True, "max_a": 12},
    {"host": "sim-tapo-1", "model": "Tapo P110 (محاكى)", "meters": True, "max_a": 16},
    {"host": "sim-tuya-1", "model": "Smart Life 16A (محاكى)", "meters": True, "max_a": 16},
    {"host": "sim-sonoff-1", "model": "Sonoff S26 DIY (محاكى)", "meters": False, "max_a": 10},
]

# host -> {"on": bool, "watts": float}. In memory; the backend re-attaches the plugs at start-up.
_STATE: dict[str, dict] = {}
_LOCK = threading.Lock()


def _known(host: str) -> dict:
    for c in CATALOG:
        if c["host"] == host:
            return c
    raise PlugError("المقبس المحاكى مش موجود.")


def attach(host: str, kind: str, on: bool = True) -> None:
    """The user 'plugged' a device of this kind into the simulated plug."""
    _known(host)
    with _LOCK:
        _STATE[host] = {"on": bool(on), "watts": round(TYPICAL_W.get(kind, 75) * random.uniform(0.92, 1.08))}


def detach(host: str) -> None:
    with _LOCK:
        _STATE.pop(host, None)


def load_w(host: str) -> float:
    """What the simulated plug really draws now (the simulator adds it to the main meter)."""
    s = _STATE.get(host)
    return float(s["watts"]) if s and s["on"] else 0.0


def status(host: str, options: dict) -> PlugStatus:
    c = _known(host)
    with _LOCK:
        s = dict(_STATE.get(host) or {"on": False, "watts": 0})
    w = s["watts"] * random.uniform(0.97, 1.03) if s["on"] else 0.0
    return PlugStatus(on=bool(s["on"]), power_w=round(w, 1) if c["meters"] else None,
                      voltage_v=round(random.uniform(228, 231), 1) if c["meters"] else None)


def switch(host: str, options: dict, on: bool) -> None:
    _known(host)
    with _LOCK:
        s = _STATE.setdefault(host, {"on": False, "watts": 0})
        s["on"] = bool(on)


def scan() -> list[dict]:
    return [{"brand": BRAND, "host": c["host"], "model": c["model"], "options": {"max_a": c["max_a"]},
             "uid": c["host"], "meters": c["meters"]} for c in CATALOG]
