"""Smart-plug drivers, one small file per brand, all on the local network.

    shelly     Shelly Plug S / Plus Plug S        local HTTP API, measures watts
    tplink     TP-Link Tapo / Kasa                python-kasa, most "energy" models measure
    tuya       Tuya / Smart Life (cheap brands)   tinytuya + a local key taken once
    tasmota    Sonoff (or any plug) with Tasmota  local HTTP, measures if the plug can
    sonoff     Sonoff DIY / LAN mode              local HTTP, on/off only
    simulated  simulated plugs for the demo       synthetic data, no hardware

To add a brand: write a file with status(), switch() and probe() or scan(), then list it here.
"""

from backend.plugs import kasa_tapo, shelly, simulated, sonoff, tasmota, tuya
from backend.plugs.base import PlugError, PlugStatus  # noqa: F401  (re-exported)

DRIVERS = {
    "shelly": shelly,
    "tplink": kasa_tapo,
    "tuya": tuya,
    "tasmota": tasmota,
    "sonoff": sonoff,
    "simulated": simulated,
}

# What the "add device" screen shows when the user picks a brand by hand.
# fields: extra things the user must type (besides the IP address).
BRANDS = [
    {"key": "shelly", "name": "Shelly", "meters": True,
     "how": "الأسهل: إله API محلي على الـ Wi-Fi وبيقيس الواط. بس اكتب الـ IP.",
     "fields": [{"key": "password", "label": "كلمة السر (إذا حطّيت حماية)", "optional": True}]},
    {"key": "tplink", "name": "TP-Link Tapo / Kasa", "meters": True,
     "how": "Kasa بيشتغل مباشرة. Tapo بدّه إيميل وكلمة سر حساب TP-Link بملف .env مرة وحدة. الموديلات P110 / KP115 بتقيس.",
     "fields": []},
    {"key": "tuya", "name": "Tuya / Smart Life", "meters": True,
     "how": "أغلب الماركات الرخيصة. بيشتغل محليًا بعد ما ناخد Device ID و Local Key مرة وحدة (tinytuya wizard).",
     "fields": [{"key": "device_id", "label": "Device ID"},
                {"key": "local_key", "label": "Local Key", "secret": True},
                {"key": "version", "label": "النسخة (3.3 أو 3.4)", "optional": True}]},
    {"key": "tasmota", "name": "Sonoff + Tasmota", "meters": True,
     "how": "Sonoff (أو أي مقبس) عليه برنامج Tasmota: محلي بالكامل، وبيقيس إذا المقبس فيه حسّاس.",
     "fields": [{"key": "password", "label": "كلمة السر (إذا في)", "optional": True}]},
    {"key": "sonoff", "name": "Sonoff DIY (LAN)", "meters": False,
     "how": "وضع DIY من Sonoff: تشغيل وإطفاء محلي بس، بدون قياس واط. (eWeLink بدّه إنترنت، فما بنعتمد عليه.)",
     "fields": []},
    {"key": "simulated", "name": "مقبس محاكى (للعرض)", "meters": True,
     "how": "مقبس وهمي ببيانات تركيبية، عشان نجرّب بدون أجهزة.", "fields": []},
]

# Rated current most plugs carry if the user does not say otherwise. 230 V in Jordan.
DEFAULT_MAX_A = 10
VOLTS = 230


def driver(brand: str):
    d = DRIVERS.get(brand)
    if d is None:
        raise PlugError("ماركة المقبس مش معروفة.")
    return d


def brand_name(brand: str) -> str:
    return next((b["name"] for b in BRANDS if b["key"] == brand), brand)
