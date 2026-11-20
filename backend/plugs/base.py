"""Shared pieces for the smart-plug drivers.

A "driver" knows how to talk to one brand of WiFi smart plug on the LOCAL
network (no cloud, no internet). Every driver has the same three functions:

    status(host, options) -> PlugStatus   read on/off and (if the plug can) watts
    switch(host, options, on)             turn the plug on or off
    probe(host, timeout)  -> dict | None  "is this IP one of my plugs?" (for the scan)

The backend never asks the LLM to talk to a plug. Every switch still goes
through the Policy Guard and, for the agent, through the human approval.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

TIMEOUT_S = 2.0   # a plug that does not answer in 2 s counts as offline for this round


# Typical power per device type, used only as a first guess until the plug (or the
# main meter) measures the real value. Also what the simulated plugs draw.
TYPICAL_W = {"ac": 1100, "fan": 45, "light": 30, "heater": 2000, "tv": 110, "washer": 600, "pc": 180,
             "router": 12, "fridge": 150, "medical": 80, "other": 75}


class PlugError(Exception):
    """The plug did not answer, refused, or the library is missing. Message is Arabic."""


@dataclass
class PlugStatus:
    on: bool
    power_w: float | None = None      # None = this plug cannot measure
    energy_kwh: float | None = None   # the plug's own total counter, if it has one
    voltage_v: float | None = None


def http_json(method: str, url: str, body: dict | None = None, timeout: float = TIMEOUT_S,
              auth: tuple[str, str] | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    if auth and auth[0]:
        import base64
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise PlugError("طلب المقبس كلمة سر. أضفها في الإعدادات أو ألغِ الحماية من تطبيق الشركة.")
        raise PlugError(f"ردّ المقبس بخطأ ({exc.code}).")
    except (urllib.error.URLError, OSError, TimeoutError):
        raise PlugError("لم يردّ المقبس. تأكد أنه يعمل وعلى شبكة الـ Wi-Fi نفسها.")
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        raise PlugError("ردّ المقبس غير مفهوم (ربما الماركة مختلفة).")


def num(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
