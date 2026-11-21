"""The live savings counter: dinars, kg of CO2, and "if 1000 Jordanian homes used it".

Rules (from CLAUDE.md, "Never invent numbers"):
- Savings count ONLY energy from actions the meter already confirmed
  (devices.agent_off == verified). backend/actions.ingest adds them up.
- Dinars use this home's real tariff tier (config/tariff.json, marginal price).
- CO2 uses the grid emission factor in config/tariff.json, with its source.
  If the factor is missing, CO2 is shown as "—", never guessed.
- The 1000-homes number is a projection, clearly labelled as one:
  (today's measured saving) x 365 days x 1000 homes. It is not a result.
"""

import time

HOMES = 1000
DAYS_PER_YEAR = 365


def today_key(meter_ts: float) -> str:
    """The day on the site's clock (the simulator can run faster than real time)."""
    return time.strftime("%Y-%m-%d", time.localtime(meter_ts))


def add_today(day_state: dict | None, meter_ts: float, wh: float) -> dict:
    """Add measured Wh to today's counter, starting again at midnight."""
    day = today_key(meter_ts)
    if not day_state or day_state.get("day") != day:
        day_state = {"day": day, "wh": 0.0}
    return {"day": day, "wh": day_state["wh"] + wh}


def today_wh(day_state: dict | None, meter_ts: float) -> float:
    if not day_state or day_state.get("day") != today_key(meter_ts):
        return 0.0
    return float(day_state["wh"])


def projection(today_kwh: float, price_jod_per_kwh: float, co2_kg_per_kwh: float | None) -> dict | None:
    """If 1000 homes saved what this home saved today, every day for a year."""
    if today_kwh <= 0:
        return None
    kwh = today_kwh * DAYS_PER_YEAR * HOMES
    return {
        "homes": HOMES,
        "kwh_year": round(kwh),
        "mwh_year": round(kwh / 1000, 1),
        "jod_year": round(kwh * price_jod_per_kwh),
        "co2_t_year": None if co2_kg_per_kwh is None else round(kwh * co2_kg_per_kwh / 1000, 1),
        "how_ar": (f"توفير اليوم المُقاس ({today_kwh:.3f} ك.و.س) × {DAYS_PER_YEAR} يوم × {HOMES} بيت. "
                   "هذا تقدير وليس نتيجة مضمونة، ويفترض أن كل بيت يوفّر قدر ما وفّرناه اليوم."),
    }


def savings(total_wh: float, today: float, held_off_w: float, price: float, tariff: dict) -> dict:
    """Everything the savings counter shows."""
    co2 = tariff.get("co2_kg_per_kwh")
    kwh, today_kwh = total_wh / 1000, today / 1000
    return {
        "kwh": round(kwh, 3),
        "jod": round(kwh * price, 3),
        "co2_kg": None if co2 is None else round(kwh * co2, 3),
        "today_kwh": round(today_kwh, 4),
        "today_jod": round(today_kwh * price, 4),
        "today_co2_kg": None if co2 is None else round(today_kwh * co2, 4),
        "rate_w": round(held_off_w),                     # verified watts held off right now
        "rate_jod_per_hour": round(held_off_w / 1000 * price, 4),
        "price_jod_per_kwh": price,
        "co2_kg_per_kwh": co2,
        "co2_source": tariff.get("co2_source"),
        "price_source": tariff.get("price_source"),
        "projection": projection(today_kwh, price, co2),
    }
