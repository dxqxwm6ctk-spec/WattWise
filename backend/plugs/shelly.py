"""Shelly plugs (Plug S, Plus Plug S, Plug US...). Local HTTP API, works with no internet.

Gen 1:  GET /relay/0?turn=on|off      GET /status  -> relays[0].ison, meters[0].power
Gen 2+: GET /rpc/Switch.Set?id=0&on=true|false
        GET /rpc/Switch.GetStatus?id=0 -> output, apower (W), voltage, aenergy.total (Wh)
Every Shelly answers GET /shelly with its model and generation, which is how the scan finds it.
Docs: https://shelly-api-docs.shelly.cloud
"""

from backend.plugs.base import PlugError, PlugStatus, http_json, num

BRAND = "shelly"


def _auth(options: dict):
    return (options.get("username") or "admin", options.get("password") or "") if options.get("password") else None


def _gen(host: str, options: dict) -> int:
    if options.get("gen"):
        return int(options["gen"])
    info = http_json("GET", f"http://{host}/shelly")
    return int(info.get("gen") or 1)


def status(host: str, options: dict) -> PlugStatus:
    auth = _auth(options)
    if _gen(host, options) >= 2:
        s = http_json("GET", f"http://{host}/rpc/Switch.GetStatus?id=0", auth=auth)
        if "output" not in s:
            raise PlugError("جهاز Shelly هذا لا يحتوي مفتاحًا (Switch).")
        total_wh = num((s.get("aenergy") or {}).get("total"))
        return PlugStatus(on=bool(s["output"]), power_w=num(s.get("apower")),
                          energy_kwh=None if total_wh is None else total_wh / 1000,
                          voltage_v=num(s.get("voltage")))
    s = http_json("GET", f"http://{host}/status", auth=auth)
    relays = s.get("relays") or []
    if not relays:
        raise PlugError("جهاز Shelly هذا لا يحتوي ريليه.")
    meter = (s.get("meters") or [{}])[0]
    total_wmin = num(meter.get("total"))   # Gen 1 counts in watt-minutes
    return PlugStatus(on=bool(relays[0].get("ison")), power_w=num(meter.get("power")),
                      energy_kwh=None if total_wmin is None else total_wmin / 60000)


def switch(host: str, options: dict, on: bool) -> None:
    auth = _auth(options)
    if _gen(host, options) >= 2:
        http_json("GET", f"http://{host}/rpc/Switch.Set?id=0&on={'true' if on else 'false'}", auth=auth)
    else:
        http_json("GET", f"http://{host}/relay/0?turn={'on' if on else 'off'}", auth=auth)


def probe(host: str, timeout: float) -> dict | None:
    try:
        info = http_json("GET", f"http://{host}/shelly", timeout=timeout)
    except PlugError:
        return None
    model = info.get("model") or info.get("type") or info.get("app")
    if not model or not (info.get("mac") or info.get("id")):
        return None
    gen = int(info.get("gen") or 1)
    return {"brand": BRAND, "host": host, "model": str(model), "options": {"gen": gen},
            "uid": str(info.get("mac") or info.get("id")), "meters": True}
