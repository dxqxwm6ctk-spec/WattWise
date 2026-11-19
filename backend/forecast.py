"""Short-horizon load forecast (AI layer 2), plain statistics.

For "this hour and the next few hours" we blend two simple guesses:

  1. NOW: the power right now. Good for the next minutes, it fades with time.
  2. PROFILE: the average power at that hour of the day, learned from the
     meter over the last 7 days (on the site's clock).

    forecast(k) = a_k * now + (1 - a_k) * profile(hour k),   a_k = 0.5 ** k

So hour 1 trusts "now" by 50%, hour 2 by 25%, hour 3 by 12.5% ... and later
hours lean on the daily pattern. If an hour has no history yet, we use "now".

We also measure our own accuracy, honestly: at the start of every hour we
write down the forecast for that hour; when the hour ends we compare it with
what the meter really measured, and keep the last 24 errors.
"""

import time

from backend import billing, config, db

HORIZON_H = 6
HISTORY_DAYS = 7
MIN_SAMPLES = 20          # readings needed before an hour's profile is trusted
CACHE_S = 10

_cache: dict[str, tuple[float, dict]] = {}


def _hour_start(ts: float) -> float:
    lt = time.localtime(ts)
    return ts - lt.tm_min * 60 - lt.tm_sec - (ts % 1)


def hourly_profile(conn, site: str, before_ts: float) -> dict[int, dict]:
    """Average power per hour of day, from finished hours only (no peeking)."""
    rows = conn.execute(
        "SELECT CAST(strftime('%H', meter_ts, 'unixepoch', 'localtime') AS INTEGER) AS h, "
        "AVG(power_w) AS w, COUNT(*) AS n FROM meter_readings "
        "WHERE site=? AND meter_ts>=? AND meter_ts<? GROUP BY h",
        (site, before_ts - HISTORY_DAYS * 86400, before_ts)).fetchall()
    return {r["h"]: {"w": r["w"], "n": r["n"]} for r in rows if r["n"] >= MIN_SAMPLES}


def _now_power(conn, site: str, meter_ts: float) -> float | None:
    """Average power over the last 5 minutes on the site's clock."""
    row = conn.execute("SELECT AVG(power_w) AS w FROM meter_readings WHERE site=? AND meter_ts>=?",
                       (site, meter_ts - 300)).fetchone()
    return row["w"]


def forecast(conn, site: str, hours: int = HORIZON_H) -> dict | None:
    """Tool: expected average power for this hour and the next ones, with kWh and JOD."""
    meter = db.latest_meter(conn, site)
    if not meter:
        return None
    now_w = _now_power(conn, site, meter["meter_ts"])
    if now_w is None:
        return None
    hs = _hour_start(meter["meter_ts"])
    profile = hourly_profile(conn, site, hs)
    steps = []
    for k in range(1, hours + 1):
        t = hs + (k - 1) * 3600
        hour = time.localtime(t).tm_hour
        a = 0.5 ** k
        prof = profile.get(hour)
        w = a * now_w + (1 - a) * prof["w"] if prof else now_w
        steps.append({"hour": f"{hour:02d}:00", "power_w": round(w), "method": "profile+now" if prof else "now"})
    kwh = sum(s["power_w"] for s in steps) / 1000
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    price = billing.marginal_price(meter.get("energy_kwh") or 0.0, tariff, ttype)
    return {"steps": steps, "kwh": round(kwh, 2), "jod": round(kwh * price, 3),
            "price_jod_per_kwh": price, "profile_hours": len(profile), "accuracy": accuracy(conn, site)}


def cached(conn, site: str) -> dict | None:
    """Same as forecast(), recomputed at most every CACHE_S seconds (the UI polls every second)."""
    hit = _cache.get(site)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    f = forecast(conn, site)
    _cache[site] = (time.time(), f)
    return f


def track(conn, site: str) -> None:
    """Called by the agent loop: score last hour's forecast, write down this hour's."""
    meter = db.latest_meter(conn, site)
    if not meter:
        return
    hs = _hour_start(meter["meter_ts"])
    st = db.get_state(conn, f"forecast_track:{site}", None) or {"hour_start": None, "pred_w": None, "errors": []}
    if st["hour_start"] == hs:
        return
    if st["pred_w"] is not None and st["hour_start"] == hs - 3600:
        row = conn.execute("SELECT AVG(power_w) AS w, COUNT(*) AS n FROM meter_readings "
                           "WHERE site=? AND meter_ts>=? AND meter_ts<?", (site, hs - 3600, hs)).fetchone()
        if row["n"] >= MIN_SAMPLES and row["w"]:
            st["errors"] = (st["errors"] + [{
                "hour": time.strftime("%H:00", time.localtime(hs - 3600)),
                "pred_w": round(st["pred_w"]), "actual_w": round(row["w"]),
                "err_pct": round(abs(st["pred_w"] - row["w"]) / row["w"] * 100, 1)}])[-24:]
    f = forecast(conn, site, hours=1)
    st.update(hour_start=hs, pred_w=f and f["steps"][0]["power_w"])
    db.set_state(conn, f"forecast_track:{site}", st)


def accuracy(conn, site: str) -> dict:
    st = db.get_state(conn, f"forecast_track:{site}", None) or {"errors": []}
    errs = st["errors"]
    if not errs:
        return {"hours": 0, "mean_err_pct": None, "last": None}
    return {"hours": len(errs), "mean_err_pct": round(sum(e["err_pct"] for e in errs) / len(errs), 1),
            "last": errs[-1]}
