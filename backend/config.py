"""Central settings for WattWise.

Values come from environment variables (or a .env file) so nothing secret is
committed. Defaults are chosen to be safe for a demo.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Tiny .env reader so we do not need an extra dependency."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


DB_PATH = Path(os.environ.get("WATTWISE_DB", ROOT / "wattwise.db"))
SITES_FILE = ROOT / "config" / "sites.json"
TARIFF_FILE = ROOT / "config" / "tariff.json"

# --- Policy Guard settings (enforced in code, never by the LLM) ---

# Critical load kinds. Blocked for everyone, always (Tier 2), even if a config
# file by mistake marks them as T1.
FORBIDDEN_KINDS = {"fridge", "fire_alarm", "medical", "emergency_light"}

# Device kinds that cool a room. Switching them off can break comfort.
COOLING_KINDS = {"ac", "fan"}

COMFORT_MIN_TEMP_C = _env_float("COMFORT_MIN_TEMP_C", 22.0)
COMFORT_MAX_TEMP_C = _env_float("COMFORT_MAX_TEMP_C", 27.0)

# Below this light reading (0..4095, LDR) an occupied room counts as dark.
DARK_LIGHT_LEVEL = _env_float("DARK_LIGHT_LEVEL", 1200)

# --- Agent timing (real seconds) ---

# An approval request with no answer in this time expires: no action.
APPROVAL_TIMEOUT_S = _env_float("APPROVAL_TIMEOUT_S", 45)

# A load running in an empty room for this long counts as waste.
WASTE_EMPTY_S = _env_float("WASTE_EMPTY_S", 3)

# Time between "waste detected" and "proposal sent", so the human can follow.
ANALYZE_S = _env_float("ANALYZE_S", 2.5)

# After an action, wait this long and then check the meter.
VERIFY_AFTER_S = _env_float("VERIFY_AFTER_S", 3)

# After a rejection or timeout, do not ask again about the same device for this long.
ASK_COOLDOWN_S = _env_float("ASK_COOLDOWN_S", 120)

# If a site sends nothing for this long, treat it as a sensor/connection fault.
STALE_READING_S = _env_float("STALE_READING_S", 15)

# How often the agent loop runs.
AGENT_INTERVAL_S = _env_float("AGENT_INTERVAL_S", 1)


def load_sites() -> dict:
    return json.loads(SITES_FILE.read_text(encoding="utf-8"))["sites"]


def load_tariff() -> dict:
    return json.loads(TARIFF_FILE.read_text(encoding="utf-8"))
