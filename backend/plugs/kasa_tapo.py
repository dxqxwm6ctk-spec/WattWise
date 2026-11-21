"""TP-Link Kasa and Tapo plugs (HS100/HS110/KP115, Tapo P100/P110...), on the local network.

Uses the open-source python-kasa library (pip install python-kasa).
- Kasa plugs work with no account.
- Tapo plugs (and newer Kasa firmware) need the TP-Link account email and password
  ONCE, to open the local connection. Put them in .env (never in the code):
      TPLINK_USERNAME=...   TPLINK_PASSWORD=...
  After that the traffic stays on the local Wi-Fi.
Models with "energy monitoring" (KP115, HS110, P110, P115) also give watts.
Docs: https://python-kasa.readthedocs.io
"""

import asyncio
import os

from backend.plugs.base import PlugError, PlugStatus, num

BRAND = "tplink"
TIMEOUT_S = 5


def _lib():
    try:
        import kasa  # noqa: F401
        return kasa
    except ImportError:
        raise PlugError("مكتبة python-kasa غير مثبّتة. نفّذ: pip install python-kasa")


def _credentials(kasa):
    user, pw = os.environ.get("TPLINK_USERNAME", ""), os.environ.get("TPLINK_PASSWORD", "")
    return kasa.Credentials(user, pw) if user and pw else None


async def _connect(host: str):
    kasa = _lib()
    dev = await kasa.Discover.discover_single(host, credentials=_credentials(kasa), timeout=TIMEOUT_S)
    if dev is None:
        raise PlugError("لم نجد مقبس TP-Link على هذا العنوان.")
    await dev.update()
    return dev


def _energy(dev):
    try:
        import kasa
        return dev.modules.get(kasa.Module.Energy)
    except Exception:   # older library versions
        return None


def _run(coro):
    try:
        return asyncio.run(asyncio.wait_for(coro, TIMEOUT_S + 2))
    except PlugError:
        raise
    except Exception as exc:
        if "auth" in type(exc).__name__.lower() or "auth" in str(exc).lower():
            raise PlugError("مقبس Tapo يحتاج بريد وكلمة سر حساب TP-Link في ملف .env (مرة واحدة).")
        raise PlugError("لم يردّ مقبس TP-Link. تأكد أنه على شبكة الـ Wi-Fi نفسها.")


def status(host: str, options: dict) -> PlugStatus:
    async def go():
        dev = await _connect(host)
        try:
            e = _energy(dev)
            return PlugStatus(on=bool(dev.is_on),
                              power_w=num(getattr(e, "current_consumption", None)) if e else None,
                              energy_kwh=num(getattr(e, "consumption_total", None)) if e else None,
                              voltage_v=num(getattr(e, "voltage", None)) if e else None)
        finally:
            await dev.disconnect()
    return _run(go())


def switch(host: str, options: dict, on: bool) -> None:
    async def go():
        dev = await _connect(host)
        try:
            await (dev.turn_on() if on else dev.turn_off())
        finally:
            await dev.disconnect()
    _run(go())


def scan(timeout: float) -> list[dict]:
    """Broadcast discovery (UDP). Returns [] if the library is missing."""
    try:
        kasa = _lib()
    except PlugError:
        return []

    async def go():
        found = await kasa.Discover.discover(timeout=timeout, credentials=_credentials(kasa))
        out = []
        for host, dev in found.items():
            try:
                await dev.update()
                model, uid, meters = dev.model, dev.mac, _energy(dev) is not None
            except Exception:   # a Tapo without credentials: still show it
                model, uid, meters = getattr(dev, "model", None) or "TP-Link", host, False
            out.append({"brand": BRAND, "host": host, "model": str(model), "options": {},
                        "uid": str(uid), "meters": meters})
            try:
                await dev.disconnect()
            except Exception:
                pass
        return out
    try:
        return asyncio.run(asyncio.wait_for(go(), timeout + 4))
    except Exception:
        return []
