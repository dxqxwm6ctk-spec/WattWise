"""Anomaly detection (AI layer 1), plain statistics, no extra library.

Idea: we know each device's load signature (watts, learned from the meter).
So at any moment we can say what the meter SHOULD read:

    expected_w = sum of the signatures of the devices that are on
    residual_w = meter_w - expected_w

In a normal house the residual is small and steady (fridge cycling, noise,
small unknown loads). We learn its normal mean and spread separately for each
hour of the day and each occupancy state (somebody home / nobody home), with a
running mean and variance (Welford's method, one row per bucket in SQLite).

A reading is unusual when the residual leaves the band
    mean +- max(K_SIGMA * std, MIN_DEVIATION_W).
When that lasts for CONFIRM_READINGS readings in a row, we raise one alert
(tier 0: only a message, the agent switches nothing). When readings stay normal
for CONFIRM_READINGS in a row, the alert closes.

Unusual readings are not learned, so a long anomaly does not become "normal".
"""

import math
import time

from backend import db

K_SIGMA = 4.0            # how many standard deviations count as unusual
MIN_DEVIATION_W = 150.0  # ignore deviations smaller than this (noise, fridge cycling)
MIN_STD_W = 10.0
WARMUP_SAMPLES = 30      # readings needed before a bucket is trusted
CONFIRM_READINGS = 5     # readings in a row before raising / clearing an alert


def _bucket(hour: int, occupied: bool) -> str:
    return f"{hour:02d}:{'occ' if occupied else 'empty'}"


def _stats(conn, site: str, bucket: str) -> dict:
    row = db.one(conn.execute("SELECT n, mean, m2 FROM anomaly_stats WHERE site=? AND bucket=?", (site, bucket)))
    return row or {"n": 0, "mean": 0.0, "m2": 0.0}


def _learn(conn, site: str, bucket: str, x: float) -> None:
    """Welford's running mean / variance update."""
    s = _stats(conn, site, bucket)
    n = s["n"] + 1
    delta = x - s["mean"]
    mean = s["mean"] + delta / n
    m2 = s["m2"] + delta * (x - mean)
    conn.execute("INSERT INTO anomaly_stats (site, bucket, n, mean, m2) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(site, bucket) DO UPDATE SET n=excluded.n, mean=excluded.mean, m2=excluded.m2",
                 (site, bucket, n, mean, m2))


def expected_w(conn, site: str) -> float:
    return sum(d["signature_w"] for d in db.devices(conn, site) if d["is_on"])


def band(conn, site: str, hour: int, occupied: bool) -> dict | None:
    """Normal band of the residual for this hour and occupancy (falls back to all hours)."""
    for bucket in (_bucket(hour, occupied), "all"):
        s = _stats(conn, site, bucket)
        if s["n"] >= WARMUP_SAMPLES:
            std = max(MIN_STD_W, math.sqrt(s["m2"] / (s["n"] - 1)))
            return {"bucket": bucket, "n": s["n"], "mean": s["mean"], "std": std,
                    "limit": max(K_SIGMA * std, MIN_DEVIATION_W)}
    return None


def observe(conn, site: str, power_w: float, meter_ts: float, occupied: bool, learning: bool = False) -> None:
    """Called for every meter reading."""
    if learning:   # a new device is being measured: its watts are not in the model yet
        return
    hour = time.localtime(meter_ts).tm_hour
    exp = expected_w(conn, site)
    residual = power_w - exp
    b = band(conn, site, hour, occupied)
    unusual = b is not None and abs(residual - b["mean"]) > b["limit"]

    if not unusual:
        _learn(conn, site, _bucket(hour, occupied), residual)
        _learn(conn, site, "all", residual)

    st = db.get_state(conn, f"anomaly:{site}", None) or {"open": False, "streak": 0}
    if unusual == st["open"]:
        st["streak"] = 0
    else:
        st["streak"] += 1
    if unusual and st["open"]:
        st.update(residual_w=round(residual - b["mean"]), power_w=round(power_w), expected_w=round(exp + b["mean"]))

    if st["streak"] >= CONFIRM_READINGS:
        st["streak"] = 0
        if unusual:
            extra = residual - b["mean"]
            st.update(open=True, since=time.time(), kind="extra" if extra > 0 else "missing",
                      residual_w=round(extra), power_w=round(power_w), expected_w=round(exp + b["mean"]),
                      hour=hour, occupied=occupied)
            if extra > 0:
                msg = (f"شذوذ: العدّاد بيقرأ ≈ {round(power_w)} واط، والمتوقع ≈ {round(exp + b['mean'])} واط "
                       f"(زيادة ≈ {round(extra)} واط). ممكن جهاز مش مسجّل أو جهاز عم يسحب أكثر من عادته.")
            else:
                msg = (f"شذوذ: العدّاد أقل من المتوقع بـ≈ {round(-extra)} واط. "
                       "ممكن جهاز فاصل أو معطّل وهو مفروض شغّال.")
            db.audit(conn, site, "T0", "agent", "anomaly", msg,
                     {"power_w": round(power_w), "expected_w": round(exp + b["mean"]),
                      "deviation_w": round(extra), "limit_w": round(b["limit"]),
                      "bucket": b["bucket"], "samples": b["n"]})
        else:
            st.update(open=False)
            db.audit(conn, site, "OK", "agent", "anomaly_cleared", "رجع الاستهلاك ضمن الطبيعي.")
    db.set_state(conn, f"anomaly:{site}", st)


def status(conn, site: str) -> dict:
    """For the UI: the open alert (if any) and how much the model has learned."""
    st = db.get_state(conn, f"anomaly:{site}", None) or {"open": False}
    n = _stats(conn, site, "all")["n"]
    out = {"open": bool(st.get("open")), "samples": n, "ready": n >= WARMUP_SAMPLES}
    if out["open"]:
        out.update({k: st.get(k) for k in ("kind", "residual_w", "power_w", "expected_w", "since")})
    return out


def clear(conn, site: str) -> None:
    db.set_state(conn, f"anomaly:{site}", None)
