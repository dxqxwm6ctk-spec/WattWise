"""Electricity bill math for Jordanian tiered household tariffs.

Tiers come from config/tariff.json. Each tier is [upper_kwh, price_jod_per_kwh];
an upper of null means "and above".
"""

import math

from backend import config


def _tiers(tariff: dict, ttype: str) -> list[tuple[float, float]]:
    raw = tariff["types"][ttype]["tiers"]
    return [(math.inf if cap is None else float(cap), float(price)) for cap, price in raw]


def bill_for(kwh: float, tariff: dict, ttype: str) -> float:
    """Energy charge in JOD for `kwh` consumed in one month."""
    total, prev = 0.0, 0.0
    for cap, price in _tiers(tariff, ttype):
        total += max(0.0, min(kwh, cap) - prev) * price
        if kwh <= cap:
            break
        prev = cap
    return total


def marginal_price(kwh: float, tariff: dict, ttype: str) -> float:
    """Price of the next kWh at this month's consumption (the tier you are in)."""
    for cap, price in _tiers(tariff, ttype):
        if kwh <= cap:
            return price
    return _tiers(tariff, ttype)[-1][1]


def tier_info(kwh: float, projected_kwh: float, tariff: dict, ttype: str) -> dict:
    """Segments for the tier bar, plus a short Arabic message about the next tier."""
    t = tariff["types"][ttype]
    tiers = _tiers(tariff, ttype)
    display_max = t["display_max_kwh"]
    segs, prev = [], 0.0
    for cap, price in tiers:
        top = min(cap, display_max)
        segs.append({
            "from_kwh": prev, "to_kwh": None if cap == math.inf else cap,
            "width_pct": round((top - prev) / display_max * 100, 1),
            "fils": round(price * 1000),
            "active": prev < kwh <= cap or (kwh == 0 and prev == 0),
        })
        prev = cap

    idx = next(i for i, (cap, _) in enumerate(tiers) if kwh <= cap)
    cap, price = tiers[idx]
    nxt = tiers[idx + 1] if idx + 1 < len(tiers) else None
    fils = round(price * 1000)
    if nxt and cap - kwh < 60:
        msg = f"بقي {round(cap - kwh)} ك.و.س على دخول شريحة {round(nxt[1] * 1000)} فلس، وكل ك.و.س بعدها أغلى."
    elif nxt and projected_kwh > cap:
        msg = f"أنت في شريحة {fils} فلس، وبهذا المعدّل ستدخل شريحة {round(nxt[1] * 1000)} فلس قبل آخر الشهر."
    else:
        msg = f"أنت في شريحة {fils} فلس، وكل ك.و.س توفّره يوفّر لك {fils} فلس."
    return {"segments": segs, "message": msg, "display_max_kwh": display_max}


def co2_factor() -> float | None:
    return config.load_tariff().get("co2_kg_per_kwh")
