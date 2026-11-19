"""Measurement & Verification (M&V) of savings, in the spirit of IPMVP Option C.

Question: how much would the site have used WITHOUT the agent?

1. Baseline period = every reading before the first action the human approved.
   Reporting period = every reading after it.
2. We cut the meter data into 15-minute intervals (on the site's clock) and,
   for each one, compute: average power, hour of day, share of rooms occupied,
   average indoor temperature.
3. On the baseline period we fit a small regression (Ridge) that predicts the
   power from hour, occupancy and temperature. That is the baseline model.
4. In the reporting period we feed the model the REAL hour, occupancy and
   temperature of each interval: it says what the site would have used
   ("adjusted baseline"). Savings = adjusted baseline - what the meter measured.

We only report savings when the model is good enough (ASHRAE Guideline 14
limits for hourly data: CV(RMSE) <= 30 % and |NMBE| <= 10 %) and there is
enough baseline data. Otherwise we say so, and show no number.
Negative savings are shown as they are.
"""

import bisect
import math
import time

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend import billing, config, db

INTERVAL_S = 15 * 60          # on the site's clock
MIN_READINGS = 5              # readings needed for an interval to count
MIN_BASELINE_INTERVALS = 12   # 3 hours of baseline before we fit anything
MAX_ROWS = 50_000
CV_RMSE_MAX = 30.0            # ASHRAE Guideline 14, hourly data
NMBE_MAX = 10.0
N_PARAMS = 5                  # 4 features + intercept
CACHE_S = 15

_cache: dict[str, tuple[float, dict]] = {}


def baseline_end(conn, site: str) -> float | None:
    """Real time of the first action the human approved (end of the baseline period)."""
    row = conn.execute("SELECT MIN(decided_ts) AS t FROM approvals WHERE site=? AND status='approved'",
                       (site,)).fetchone()
    return row["t"]


def intervals(conn, site: str) -> list[dict]:
    """15-minute intervals with power, hour, occupancy share and indoor temperature."""
    meters = db.rows(conn.execute(
        "SELECT ts, meter_ts, power_w FROM meter_readings WHERE site=? ORDER BY id DESC LIMIT ?", (site, MAX_ROWS)))
    meters.reverse()
    if not meters:
        return []
    rooms = db.rows(conn.execute(
        "SELECT ts, temp_c, occupied FROM room_readings WHERE site=? AND ts>=? ORDER BY ts",
        (site, meters[0]["ts"] - 1)))
    room_ts = [r["ts"] for r in rooms]

    buckets: dict[int, list[dict]] = {}
    for m in meters:
        buckets.setdefault(int(m["meter_ts"] // INTERVAL_S), []).append(m)

    out = []
    for key in sorted(buckets):
        ms = buckets[key]
        if len(ms) < MIN_READINGS:
            continue
        t0, t1 = ms[0]["ts"], ms[-1]["ts"]
        rs = rooms[bisect.bisect_left(room_ts, t0 - 0.5):bisect.bisect_right(room_ts, t1 + 0.5)]
        temps = [r["temp_c"] for r in rs if r["temp_c"] is not None]
        occ = [r["occupied"] for r in rs if r["occupied"] is not None]
        if not temps or not occ:
            continue
        start = key * INTERVAL_S
        out.append({
            "start": start,
            "label": time.strftime("%H:%M", time.localtime(start)),
            "hour": time.localtime(start).tm_hour + time.localtime(start).tm_min / 60,
            "power_w": sum(m["power_w"] for m in ms) / len(ms),
            "occ": sum(occ) / len(occ),
            "temp_c": sum(temps) / len(temps),
            "ts_first": t0, "ts_last": t1,
        })
    return out


def _features(rows: list[dict]) -> np.ndarray:
    return np.array([[math.sin(2 * math.pi * r["hour"] / 24), math.cos(2 * math.pi * r["hour"] / 24),
                      r["occ"], r["temp_c"]] for r in rows])


def fit(rows: list[dict]):
    """Baseline model + its quality numbers (CV(RMSE), NMBE, R²)."""
    X, y = _features(rows), np.array([r["power_w"] for r in rows])
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(X, y)
    pred = model.predict(X)
    n, mean = len(y), float(y.mean())
    resid = y - pred
    rmse = math.sqrt(float((resid ** 2).sum()) / max(1, n - N_PARAMS))
    ss_tot = float(((y - mean) ** 2).sum())
    quality = {
        "n": n,
        "cv_rmse_pct": round(rmse / mean * 100, 2) if mean else None,
        "nmbe_pct": round(float(resid.sum()) / (max(1, n - N_PARAMS) * mean) * 100, 2) if mean else None,
        "r2": round(1 - float((resid ** 2).sum()) / ss_tot, 3) if ss_tot > 1e-9 else None,
        "rmse_w": round(rmse, 1),
    }
    quality["passes"] = (quality["cv_rmse_pct"] is not None and quality["cv_rmse_pct"] <= CV_RMSE_MAX
                         and abs(quality["nmbe_pct"]) <= NMBE_MAX)
    return model, quality


def _period(r: dict, end: float | None) -> str:
    if end is None or r["ts_last"] < end:
        return "baseline"
    return "reporting" if r["ts_first"] >= end else "switch"


def compute(conn, site: str) -> dict:
    rows = intervals(conn, site)
    end = baseline_end(conn, site)
    base = [r for r in rows if _period(r, end) == "baseline"]
    report = [r for r in rows if _period(r, end) == "reporting"]
    out = {"interval_min": INTERVAL_S // 60, "baseline_intervals": len(base), "reporting_intervals": len(report),
           "baseline_end": end, "status": "", "message_ar": "", "series": []}

    if len(base) < MIN_BASELINE_INTERVALS:
        out["status"] = "not_enough_baseline"
        out["message_ar"] = (f"لسا ما في بيانات كفاية لخط الأساس ({len(base)} من {MIN_BASELINE_INTERVALS} فترة "
                             f"كل وحدة {INTERVAL_S // 60} دقيقة). ما بنعرض رقم توفير.")
        out["series"] = [{"label": r["label"], "actual_w": round(r["power_w"]), "baseline_w": None,
                          "period": _period(r, end)} for r in rows]
        return out

    model, quality = fit(base)
    out["model"] = quality
    pred_all = model.predict(_features(rows)) if rows else []
    for r, p in zip(rows, pred_all):
        period = _period(r, end)
        out["series"].append({"label": r["label"], "actual_w": round(r["power_w"]), "baseline_w": round(float(p)),
                              "period": period})

    if not quality["passes"]:
        out["status"] = "model_not_good_enough"
        out["message_ar"] = (f"نموذج خط الأساس مش دقيق كفاية (CV(RMSE) = {quality['cv_rmse_pct']}٪، "
                             f"NMBE = {quality['nmbe_pct']}٪). ما بنعرض رقم توفير لحد ما يتحسّن.")
        return out
    if not report:
        out["status"] = "no_reporting_data"
        out["message_ar"] = "النموذج جاهز. لسا ما في فترة بعد أول إجراء وافقت عليه، فما في توفير نقيسه."
        return out

    h = INTERVAL_S / 3600
    pred = model.predict(_features(report))
    actual_kwh = sum(r["power_w"] for r in report) * h / 1000
    baseline_kwh = float(pred.sum()) * h / 1000
    saved = baseline_kwh - actual_kwh
    # Rough 95 % band, assuming independent interval errors.
    band = 2 * quality["rmse_w"] * math.sqrt(len(report)) * h / 1000
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    meter = db.latest_meter(conn, site) or {}
    price = billing.marginal_price(meter.get("energy_kwh") or 0.0, tariff, ttype)
    co2 = billing.co2_factor()
    out.update({
        "status": "ok",
        "baseline_kwh": round(baseline_kwh, 3), "actual_kwh": round(actual_kwh, 3),
        "saved_kwh": round(saved, 3), "saved_band_kwh": round(band, 3),
        "saved_pct": round(saved / baseline_kwh * 100, 1) if baseline_kwh else None,
        "saved_jod": round(saved * price, 3), "price_jod_per_kwh": price,
        "saved_co2_kg": None if co2 is None else round(saved * co2, 2),
    })
    sign = "وفّرنا" if saved >= 0 else "استهلكنا زيادة"
    out["message_ar"] = (f"{sign} {abs(round(saved, 2))} ± {round(band, 2)} ك.و.س "
                         f"({abs(out['saved_pct'] or 0)}٪) مقارنة بخط الأساس المعدّل.")
    return out


def cached(conn, site: str) -> dict:
    hit = _cache.get(site)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    r = compute(conn, site)
    _cache[site] = (time.time(), r)
    return r
