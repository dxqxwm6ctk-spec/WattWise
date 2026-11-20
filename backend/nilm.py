"""NILM-lite: recognising a device from ONE meter, using watts AND power factor.

The PZEM-004T gives real power P (watts) and the power factor PF.
From those two we get the reactive power Q (VAR):

    Q = P * tan(acos(PF))

When a relay switches one device, the meter jumps. The jump is the device's
signature, as a point in the (P, Q) plane:

    lamp (resistive, PF ~ 1.0):    ( 40 W,  ~0 VAR)
    fan  (has a motor, PF ~ 0.8):  ( 45 W, ~34 VAR)

Two devices with almost the same watts are far apart in Q, so the agent can
still tell them apart. That is the whole idea, nothing more.
"""

import math

# A device is called "resistive" (heater, kettle, old lamp) when its PF is at least this.
RESISTIVE_PF = 0.95
# Two PF values closer than this are "the same type of load".
PF_TOLERANCE = 0.15


def reactive(p_w: float, pf: float | None) -> float | None:
    """Reactive power in VAR from real power and power factor. None if PF is unknown."""
    if pf is None or p_w is None:
        return None
    pf = min(1.0, max(0.05, abs(pf)))
    return abs(p_w) * math.tan(math.acos(pf))


def step_pf(d_p: float, d_q: float | None) -> float | None:
    """Power factor of the jump itself (the device alone, not the whole house)."""
    if d_q is None or d_p <= 0:
        return None
    s = math.hypot(d_p, max(0.0, d_q))
    return round(d_p / s, 2) if s else None


def load_type_ar(pf: float | None) -> str:
    if pf is None:
        return "نوع الحمل مش معروف (بدنا قياس PF)"
    if pf >= RESISTIVE_PF:
        return "حمل مقاومي (لمبة عادية، سخّان، غلّاية)"
    return "حمل فيه محرّك أو إلكترونيات (مروحة، مكيّف، شاحن)"


def pf_matches(expected: float | None, measured: float | None) -> bool | None:
    """True/False when both are known, None when we cannot say."""
    if expected is None or measured is None:
        return None
    return abs(expected - measured) <= PF_TOLERANCE


def match(d_p: float, d_q: float | None, devices: list[dict]) -> tuple[dict | None, float]:
    """Which known device best explains a jump of (d_p W, d_q VAR)?

    Distance in the (P, Q) plane. Devices whose PF was never measured are
    compared on watts only. Returns (device, distance) or (None, inf).
    """
    best, best_dist = None, math.inf
    for d in devices:
        p = d["signature_w"]
        pf = d.get("signature_pf")
        if d_q is not None and pf is not None:
            dist = math.hypot(d_p - p, d_q - reactive(p, pf))
        else:
            dist = abs(d_p - p)
        if dist < best_dist:
            best, best_dist = d, dist
    return best, best_dist
