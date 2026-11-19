"""Weather tool: outdoor temperature and solar radiation from Open-Meteo.

Open-Meteo is free and needs no API key. The demo must also work with no
internet, so this tool never raises: when the network is down it returns
{"available": False} and the agent simply works without the weather.
Results are cached for 15 minutes so we do not call the API every second.
"""

import json
import threading
import time
import urllib.parse
import urllib.request

from backend import config

URL = "https://api.open-meteo.com/v1/forecast"
CACHE_S = 15 * 60
TIMEOUT_S = 4

_cache: dict = {"ts": 0.0, "data": None}


def _fetch() -> dict:
    params = {
        "latitude": config.WEATHER_LAT,
        "longitude": config.WEATHER_LON,
        "current": "temperature_2m,relative_humidity_2m,shortwave_radiation",
        "hourly": "temperature_2m,shortwave_radiation",
        "forecast_days": 1,
        "timezone": "Asia/Amman",
    }
    with urllib.request.urlopen(f"{URL}?{urllib.parse.urlencode(params)}", timeout=TIMEOUT_S) as r:
        raw = json.load(r)
    cur = raw.get("current", {})
    hourly = raw.get("hourly", {})
    temps = hourly.get("temperature_2m") or []
    return {
        "available": True,
        "source": "Open-Meteo",
        "place": config.WEATHER_PLACE,
        "time": cur.get("time"),
        "outdoor_temp_c": cur.get("temperature_2m"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "solar_w_m2": cur.get("shortwave_radiation"),
        "today_max_c": max(temps) if temps else None,
        "today_min_c": min(temps) if temps else None,
    }


def get_weather(now: float | None = None) -> dict:
    """Tool: current outdoor weather. Never raises; offline means available=False."""
    now = now or time.time()
    if not config.WEATHER_ENABLED:
        return {"available": False, "reason": "disabled"}
    if _cache["data"] and now - _cache["ts"] < CACHE_S:
        return _cache["data"]
    try:
        data = _fetch()
    except Exception as e:  # no internet, DNS, timeout, bad JSON ...
        data = {"available": False, "reason": f"offline: {type(e).__name__}"}
        # Do not retry a dead network every second: try again in a minute.
        _cache.update(ts=now - CACHE_S + 60, data=data)
        return data
    _cache.update(ts=now, data=data)
    return data


_refreshing = threading.Lock()


def cached() -> dict:
    """Last known weather without touching the network (safe for the 1-second UI poll)."""
    return _cache["data"] or {"available": False, "reason": "not_yet"}


def refresh_in_background() -> None:
    """Called by the agent loop: refresh the cache in a thread when it is old."""
    if not config.WEATHER_ENABLED or time.time() - _cache["ts"] < CACHE_S:
        return
    if not _refreshing.acquire(blocking=False):
        return

    def work():
        try:
            get_weather()
        finally:
            _refreshing.release()

    threading.Thread(target=work, daemon=True, name="weather").start()
