"""Policy Guard: hard safety rules, enforced in plain code, outside the LLM.

Every device command goes through `check_switch` right before it runs.
The planner (rule-based now, LLM later) can only *propose*; this file decides.
"""

from dataclasses import dataclass

from backend import config

AGENT = "agent"
HUMAN = "human"
SCHEDULE = "schedule"   # a timer or daily schedule the human set up earlier

# Schedules and timers
MIN_WINDOW_MIN = 10          # an on/off window shorter than this is a mistake
HEATER_MAX_WINDOW_MIN = 180  # the water heater never runs more than 3 hours in one go
MAX_TIMER_MIN = 720          # timers up to 12 hours


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

    # A human may switch any non-critical device by hand.
    # Everything below is for the agent and for timers/schedules (no human pressing a button now).
    if actor == HUMAN:
        return ok()

    # Allowlist: the agent only touches devices explicitly allowed.
    # (A schedule was chosen by the human for this device, so it skips this one check.)
    if actor == AGENT and not device.get("allow"):
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


# ---------- timers and schedules (on/off only) ----------

def _minutes(hhmm: str | None) -> int | None:
    """"06:30" -> 390. None or a bad value -> None."""
    try:
        h, m = str(hhmm).strip().split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    return h * 60 + m if 0 <= h < 24 and 0 <= m < 60 else None


def window_minutes(on_time: str, off_time: str) -> int:
    """Length of an on->off window, also across midnight (22:00 -> 01:00 is 180)."""
    return (_minutes(off_time) - _minutes(on_time)) % 1440


def _can_automate(device: dict) -> Decision:
    name = device.get("name", device.get("id", "?"))
    if is_critical(device):
        return Decision(False, "critical_load", f"{name} حمل حرج (T2)، ممنوع بالكود حتى لو طلبت.")
    if device.get("sensitive"):
        return Decision(False, "sensitive_device", f"{name} جهاز حساس، ما بيندار بمؤقّت أو جدول.")
    return ok()


def check_schedule(device: dict, on_time: str | None, off_time: str | None) -> Decision:
    """May this daily on/off schedule be saved? Checked again every time it fires."""
    d = _can_automate(device)
    if not d.allowed:
        return d
    if not on_time and not off_time:
        return Decision(False, "no_time", "لازم وقت تشغيل أو وقت إطفاء.")
    if (on_time and _minutes(on_time) is None) or (off_time and _minutes(off_time) is None):
        return Decision(False, "bad_time", "الوقت مش مفهوم. اكتبه مثل 06:30.")
    if on_time and off_time:
        w = window_minutes(on_time, off_time)
        if w < MIN_WINDOW_MIN:
            return Decision(False, "window_too_short", f"المدة أقل من {MIN_WINDOW_MIN} دقايق.")
        if device.get("kind") == "heater" and w > HEATER_MAX_WINDOW_MIN:
            return Decision(False, "heater_too_long",
                            "حارس السياسات: السخّان ما بيشتغل أكثر من ٣ ساعات متواصلة.")
    return ok()


def check_timer(device: dict, minutes: int) -> Decision:
    """May this one-off timer ("switch it off after 30 minutes") be saved?"""
    d = _can_automate(device)
    if not d.allowed:
        return d
    if not isinstance(minutes, int) or minutes < 1 or minutes > MAX_TIMER_MIN:
        return Decision(False, "bad_minutes", "المدة مش مفهومة (من دقيقة لـ ١٢ ساعة).")
    return ok()
