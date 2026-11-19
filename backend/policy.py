"""Policy Guard: hard safety rules, enforced in plain code, outside the LLM.

Every device command goes through `check_switch` right before it runs.
The planner (rule-based now, LLM later) can only *propose*; this file decides.
"""

from dataclasses import dataclass

from backend import config

AGENT = "agent"
HUMAN = "human"


@dataclass
class Decision:
    allowed: bool
    code: str        # short English reason, for logs and tests
    reason_ar: str   # plain Arabic reason, shown in the UI


def ok() -> Decision:
    return Decision(True, "ok", "مسموح.")


def is_critical(device: dict) -> bool:
    """Tier 2: critical loads. Checked by kind too, so a config typo cannot unlock a fridge."""
    return device.get("tier") == "T2" or device.get("kind") in config.FORBIDDEN_KINDS


def check_switch(device: dict, turn_on: bool, actor: str, room: dict | None,
                 estop: bool = False, safe_mode: bool = False) -> Decision:
    """May `actor` switch `device` on/off right now?

    device: a row from the devices table.
    room:   the latest sensor reading of the device's room (or None).
    """
    name = device.get("name", device.get("id", "?"))

    # Tier 2: nobody touches critical loads. Not the agent, not the app.
    if is_critical(device):
        return Decision(False, "critical_load", f"{name} حمل حرج (T2) وممنوع التحكم فيه بالكود.")

    # A human may switch any non-critical device by hand. Everything below is for the agent.
    if actor == HUMAN:
        return ok()

    # Allowlist: the agent only touches devices explicitly allowed.
    if not device.get("allow"):
        return Decision(False, "not_in_allowlist", f"{name} مش ضمن القائمة المسموحة للوكيل.")

    # Sensitive devices (like the router that carries the approval app) stay manual.
    if device.get("sensitive"):
        return Decision(False, "sensitive_device", f"{name} جهاز حساس، التحكم فيه يدوي بس.")

    if estop:
        return Decision(False, "estop_active", "إيقاف الطوارئ مفعّل، الوكيل موقوف.")

    if safe_mode:
        return Decision(False, "safe_mode", "الوكيل بالوضع الآمن (ما في اتصال)، ما بينفّذ إشي.")

    # Without fresh room data we cannot know if comfort is safe: refuse.
    if room is None:
        return Decision(False, "no_sensor_data", "ما في قراءات حساسات للغرفة، ما بنقدر نتأكد إنه آمن.")

    # Turning a load ON never breaks comfort limits in this system.
    if turn_on:
        return ok()

    occupied = bool(room.get("occupied"))
    temp = room.get("temp_c")

    # Comfort: never switch cooling off on people in a room that is too hot.
    if device.get("kind") in config.COOLING_KINDS and occupied:
        if temp is None:
            return Decision(False, "no_temperature", "ما في قراءة حرارة والغرفة فيها ناس.")
        if temp >= config.COMFORT_MAX_TEMP_C:
            return Decision(False, "comfort_max_temp",
                            f"الحرارة {temp:.1f}° فوق حد الراحة ({config.COMFORT_MAX_TEMP_C:.0f}°) والغرفة فيها ناس.")

    # Comfort: never switch the light off on people sitting in the dark.
    if device.get("kind") == "light" and occupied:
        light = room.get("light")
        if light is None or light < config.DARK_LIGHT_LEVEL:
            return Decision(False, "comfort_dark", "الغرفة فيها ناس والإضاءة الطبيعية قليلة.")

    return ok()


def check_setpoint(device: dict, value: float) -> Decision:
    """AC set temperature must stay inside the comfort band, for everyone."""
    if is_critical(device):
        return Decision(False, "critical_load", "حمل حرج، ممنوع التحكم فيه.")
    if device.get("kind") != "ac":
        return Decision(False, "no_setpoint", "هذا الجهاز ما إله حرارة.")
    lo, hi = config.COMFORT_MIN_TEMP_C, config.COMFORT_MAX_TEMP_C
    if value < lo or value > hi:
        return Decision(False, "comfort_band",
                        f"ما بنقدر نضبط المكيّف على {value:g}°، برّا حدود الراحة {lo:g}–{hi:g}°.")
    return ok()


def approval_expired(created_ts: float, now: float) -> bool:
    """Silence is not consent: past the timeout, a request can no longer be approved."""
    return now - created_ts >= config.APPROVAL_TIMEOUT_S
