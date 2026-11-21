"""Understanding a goal written in plain Arabic, without any LLM (works offline).

The rule-based agent reads the goal and builds a plan that depends on what the
human actually asked for:

  "نزّل استهلاك غرفة النوم 15% هالأسبوع بدون ما نحس بالحر"
      -> target: 15 % less energy, measured with the M&V baseline
      -> focus:  the bedroom first
      -> limit:  comfort (temperature) is checked before every action
      -> period: this week

  "بدي الفاتورة ما تتعدى 25 دينار"
      -> target: bill under 25 JD (tariff tiers)

The plan's focus is used by the agent loop: waste in the rooms or device kinds
the human named is handled first. Nothing here switches anything; every action
still goes through the Policy Guard and the human's approval.
"""

import re

from backend import config, db

# Words -> device kind. Kept small on purpose (same idea as the command parser).
KIND_WORDS = {
    "ac": r"مكيف|تكييف|تبريد",
    "fan": r"مروح",
    "light": r"اناره|لمبه|لمبات|لمض|\bضو",
    "heater": r"سخان|حمام ميه|ميه سخنه",
    "tv": r"تلفزيون|شاشه",
    "pc": r"كمبيوتر|لابتوب",
    "washer": r"غسال",
}
KIND_NAMES = {"ac": "المكيّفات", "fan": "المراوح", "light": "الإنارة", "heater": "السخّان",
              "tv": "التلفزيون", "pc": "الكمبيوترات", "washer": "الغسالة"}

PERIODS = [
    (r"الليل|بالليل|ليلا", "ليلًا"),
    (r"اليوم|هاليوم", "اليوم"),
    (r"الاسبوع|هالاسبوع|اسبوع", "هذا الأسبوع"),
    (r"الشهر|هالشهر|شهر", "هذا الشهر"),
]

PERCENT_RX = r"(\d+(?:\.\d+)?)\s*(?:%|٪|بالميه|في الميه|بالمئه|بالمائه)"


def _norm(text: str) -> str:
    from backend.assistant import norm   # same Arabic normalisation as the command parser
    return norm(text)


def read_percent(text: str) -> float | None:
    """'نزّل 15%' or '١٥ بالمية' -> 15. Only 1..90 makes sense as a reduction target."""
    m = re.search(PERCENT_RX, _norm(text))
    if not m:
        return None
    value = float(m.group(1))
    return value if 1 <= value <= 90 else None


def _tokens(name: str) -> list[str]:
    words = [w[2:] if w.startswith("ال") else w for w in _norm(name).split()]
    return [w for w in words if w not in ("غرفه", "مكتب") and len(w) >= 2] or words


def _has(text: str, tok: str) -> bool:
    """Word piece inside the text; a number must stand alone ("مكتب 1" is not "15%")."""
    if tok.isdigit():
        return re.search(rf"(?<!\d){tok}(?!\d|\s*%|\s*٪)", text) is not None
    return tok in text


def understand(conn, site: str, text: str, bill_target_jd: float | None) -> dict:
    """Pull the parts of the goal out of the text. Returns plain data, no side effects."""
    t = _norm(text)
    rooms = []
    for r in db.rooms(conn, site):
        toks = _tokens(r["name"])
        # "مكتب ١" needs the number too, otherwise every office matches.
        if toks and all(_has(t, tok) for tok in toks):
            rooms.append({"id": r["id"], "name": r["name"]})
    kinds = [k for k, rx in KIND_WORDS.items() if re.search(rx, t)]
    period = next((label for rx, label in PERIODS if re.search(rx, t)), None)
    return {
        "percent": read_percent(text),
        "bill_jd": bill_target_jd,
        "rooms": rooms,
        "kinds": kinds,
        "period": period,
        "comfort": bool(re.search(r"راحه|حر|برد|نشوب|نحس|مرتاح|دافي|حراره", t)),
        "report": bool(re.search(r"تقرير|ملخص|خبرني|اعطيني", t)),
        "peak": bool(re.search(r"ذروه|غالي|الشريحه|شريحه|سخان", t)),
    }


def plan_steps(intent: dict) -> list[str]:
    """The plan in plain Arabic. Different goals give different plans."""
    steps = ["أقرأ العدّاد والحسّاسات في كل غرفة كل ثانية."]

    # What to look at first.
    focus = [r["name"] for r in intent["rooms"]] + [KIND_NAMES.get(k, k) for k in intent["kinds"]]
    if focus:
        steps.append(f"أبدأ بـ: {' و'.join(focus)} (المذكورة في الهدف)، ثم بقية المكان.")
    steps.append("أبحث عن أجهزة تعمل في غرف فارغة، وعن أي حمل غريب لا يطابق أي بصمة.")

    # Comfort limits are always enforced by the Policy Guard; say it louder if the goal mentions comfort.
    lo, hi = config.COMFORT_MIN_TEMP_C, config.COMFORT_MAX_TEMP_C
    if intent["comfort"]:
        steps.append(f"قبل أي اقتراح أتأكد أن حرارة الغرفة تبقى بين {lo:g} و{hi:g} درجة، لأنك طلبت الحفاظ على الراحة.")
    else:
        steps.append("أتأكد أن الإطفاء لا يتجاوز حدود الراحة ولا يمس جهازًا ممنوعًا.")

    if intent["peak"]:
        steps.append("أقترح جدولًا للسخّان بساعات أقصر حتى لا ننتقل إلى شريحة أغلى.")

    steps.append("أسألك قبل أي إطفاء، وإن لم تردّ فلن أفعل شيئًا.")
    steps.append("بعد التنفيذ أتحقق بالعدّاد من انخفاض الاستهلاك فعلًا.")

    # How success is measured.
    period = f" {intent['period']}" if intent["period"] else ""
    if intent["percent"]:
        steps.append(f"أقيس التوفير{period} مقابل خط الأساس (M&V) وأقارنه بهدف {intent['percent']:g}٪، "
                     "ولا أذكر رقمًا إلا إذا قِيس.")
    if intent["bill_jd"]:
        steps.append(f"أقارن الفاتورة المتوقعة بهدفك ({intent['bill_jd']:g} دينار) حسب شرائح التعرفة.")
    if not intent["percent"] and not intent["bill_jd"]:
        steps.append(f"أحسب التوفير المُقاس{period} بالدينار.")
    if intent["report"] or intent["period"]:
        steps.append("أُعدّ لك تقريرًا بالأرقام المُقاسة فقط.")
    return steps


def summary(intent: dict) -> str:
    parts = []
    if intent["percent"]:
        parts.append(f"خفض الاستهلاك {intent['percent']:g}٪")
    if intent["bill_jd"]:
        parts.append(f"الفاتورة تحت {intent['bill_jd']:g} دينار")
    if intent["rooms"] or intent["kinds"]:
        names = [r["name"] for r in intent["rooms"]] + [KIND_NAMES.get(k, k) for k in intent["kinds"]]
        parts.append("التركيز على " + " و".join(names))
    if intent["period"]:
        parts.append(intent["period"])
    if intent["comfort"]:
        parts.append("مع الحفاظ على الراحة")
    if not parts:
        return "لم أجد رقمًا أو غرفة محددة في كلامك، لذا سأراقب البيت كله وأوفّر دون هدف رقمي."
    return "فهمت: " + "، ".join(parts) + "."


def focus_rank(plan: dict | None, device: dict) -> int:
    """0 for a device the goal named (room or kind), 1 otherwise. Used to order waste candidates."""
    if not plan:
        return 1
    focus = plan.get("focus") or {}
    if device["room"] in focus.get("rooms", []) or device["kind"] in focus.get("kinds", []):
        return 0
    return 1
