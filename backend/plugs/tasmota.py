"""Plugs running Tasmota (open-source firmware). Many Sonoff plugs can be flashed with it.

GET /cm?cmnd=Power%20On|Off       -> {"POWER": "ON"}
GET /cm?cmnd=Status%2010          -> StatusSNS.ENERGY.Power / Voltage / Total (only plugs with metering)
Docs: https://tasmota.github.io/docs/Commands/
"""

import urllib.parse

from backend.plugs.base import PlugError, PlugStatus, http_json, num

BRAND = "tasmota"


def _cmd(host: str, options: dict, command: str, timeout: float | None = None) -> dict:
    q = {"cmnd": command}
    if options.get("password"):
        q["user"] = options.get("username") or "admin"
        q["password"] = options["password"]
    url = f"http://{host}/cm?" + urllib.parse.urlencode(q)
    return http_json("GET", url, **({"timeout": timeout} if timeout else {}))


def _is_on(answer: dict) -> bool:
    value = answer.get("POWER", answer.get("POWER1"))
    if value is None:
        raise PlugError("لم يردّ الجهاز بحالة التشغيل (POWER).")
    return str(value).upper() == "ON"


def status(host: str, options: dict) -> PlugStatus:
    on = _is_on(_cmd(host, options, "Power"))
    energy = (_cmd(host, options, "Status 10").get("StatusSNS") or {}).get("ENERGY") or {}
    return PlugStatus(on=on, power_w=num(energy.get("Power")), energy_kwh=num(energy.get("Total")),
                      voltage_v=num(energy.get("Voltage")))


def switch(host: str, options: dict, on: bool) -> None:
    _cmd(host, options, "Power On" if on else "Power Off")


def probe(host: str, timeout: float) -> dict | None:
    try:
        s = _cmd(host, {}, "Status 0", timeout=timeout)
    except PlugError:
        return None
    if "Status" not in s:
        return None
    net = s.get("StatusNET") or {}
    meters = bool((s.get("StatusSNS") or {}).get("ENERGY"))
    name = (s.get("Status") or {}).get("DeviceName") or "Tasmota"
    return {"brand": BRAND, "host": host, "model": str(name), "options": {},
            "uid": str(net.get("Mac") or host), "meters": meters}
