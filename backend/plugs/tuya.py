"""Tuya / Smart Life plugs (most cheap "WiFi smart plug" brands sold in Jordan).

Uses the open-source tinytuya library (pip install tinytuya), fully on the local Wi-Fi.
Each plug needs three things once: its Device ID, its Local Key and the protocol
version (3.3 for most). Get them ONCE with `python -m tinytuya wizard`
(needs a free Tuya IoT developer account and internet only for that one step).
After that, no cloud and no internet.

Data points ("DPS") on most plugs: "1" = on/off, "19" = power in 0.1 W, "20" = voltage in 0.1 V.
Some plugs use other numbers; they can be changed per plug in the options.
Docs: https://github.com/jasonacox/tinytuya
"""

from backend.plugs.base import PlugError, PlugStatus, num

BRAND = "tuya"


def _lib():
    try:
        import tinytuya
        return tinytuya
    except ImportError:
        raise PlugError("مكتبة tinytuya غير مثبّتة. نفّذ: pip install tinytuya")


def _device(host: str, options: dict):
    tinytuya = _lib()
    if not options.get("device_id") or not options.get("local_key"):
        raise PlugError("مقبس Tuya يحتاج Device ID و Local Key (مرة واحدة فقط).")
    d = tinytuya.OutletDevice(options["device_id"], host, options["local_key"],
                              version=float(options.get("version") or 3.3))
    d.set_socketTimeout(2)
    d.set_socketRetryLimit(1)
    return d


def status(host: str, options: dict) -> PlugStatus:
    s = _device(host, options).status()
    if not isinstance(s, dict) or "dps" not in s:
        raise PlugError("لم يردّ مقبس Tuya بشكل صحيح. تأكد من الـ Local Key والنسخة (3.3 / 3.4).")
    dps = s["dps"]
    sw = str(options.get("dps_switch") or "1")
    pw = str(options.get("dps_power") or "19")
    vt = str(options.get("dps_voltage") or "20")
    power = num(dps.get(pw))
    volt = num(dps.get(vt))
    return PlugStatus(on=bool(dps.get(sw)),
                      power_w=None if power is None else power / 10,
                      voltage_v=None if volt is None else volt / 10)


def switch(host: str, options: dict, on: bool) -> None:
    d = _device(host, options)
    sw = int(options.get("dps_switch") or 1)
    ans = d.turn_on(switch=sw) if on else d.turn_off(switch=sw)
    if isinstance(ans, dict) and ans.get("Error"):
        raise PlugError("مقبس Tuya رفض الأمر: " + str(ans.get("Error")))


def scan(timeout: float) -> list[dict]:
    """Tuya plugs announce themselves on UDP 6666/6667. Returns [] if the library is missing."""
    try:
        tinytuya = _lib()
        # maxretry = how many listening rounds (about 1 s each); poll=False: do not open the plugs.
        found = tinytuya.deviceScan(verbose=False, maxretry=max(2, int(timeout)), color=False, poll=False)
    except Exception:
        return []
    out = []
    for ip, info in (found or {}).items():
        out.append({"brand": BRAND, "host": ip, "model": "Tuya / Smart Life",
                    "options": {"device_id": info.get("gwId") or info.get("id") or "",
                                "version": str(info.get("version") or "3.3")},
                    "uid": str(info.get("gwId") or ip), "meters": None, "needs": ["local_key"]})
    return out
