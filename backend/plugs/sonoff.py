"""Sonoff plugs in "DIY / LAN mode" (local HTTP on port 8081, no eWeLink cloud).

POST http://IP:8081/zeroconf/switch {"deviceid": "", "data": {"switch": "on"}}
POST http://IP:8081/zeroconf/info   {"deviceid": "", "data": {}}  -> data.switch
DIY mode only switches (no watts). For watts, flash Tasmota and use the Tasmota driver.
eWeLink (the cloud app) needs internet, so we do not depend on it.
Docs: https://sonoff.tech/sonoff-diy-developer-documentation-basicr3-rfr3-mini-http-api/
"""

from backend.plugs.base import PlugError, PlugStatus, http_json

BRAND = "sonoff"
PORT = 8081


def _post(host: str, options: dict, path: str, data: dict, timeout: float | None = None) -> dict:
    body = {"deviceid": options.get("device_id", ""), "data": data}
    ans = http_json("POST", f"http://{host}:{PORT}/zeroconf/{path}", body, **({"timeout": timeout} if timeout else {}))
    if ans.get("error") not in (0, None):
        raise PlugError(f"ردّ جهاز Sonoff بخطأ ({ans.get('error')}).")
    return ans


def status(host: str, options: dict) -> PlugStatus:
    data = _post(host, options, "info", {}).get("data") or {}
    if isinstance(data, str):   # older firmware sends data as a JSON string
        import json
        data = json.loads(data)
    return PlugStatus(on=str(data.get("switch", "off")).lower() == "on")


def switch(host: str, options: dict, on: bool) -> None:
    _post(host, options, "switch", {"switch": "on" if on else "off"})


def probe(host: str, timeout: float) -> dict | None:
    try:
        ans = _post(host, {}, "info", {}, timeout=timeout)
    except PlugError:
        return None
    data = ans.get("data")
    if data is None:
        return None
    return {"brand": BRAND, "host": host, "model": "Sonoff DIY", "options": {},
            "uid": str(ans.get("deviceid") or host), "meters": False}
