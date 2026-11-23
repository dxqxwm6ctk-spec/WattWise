"""Read a photo of an electricity bill, or bill numbers typed by hand.

Two ways in:
  1. Photo  -> Claude (vision) reads the numbers printed on the bill and writes
               a short Arabic explanation. Needs ANTHROPIC_API_KEY in .env.
  2. Manual -> the owner types kWh, days and the amount. Works offline, no key.

Either way, the CODE (not the model) then:
  - checks the bill against our tariff table (config/tariff.json),
  - compares the bill's kWh per day with what our meter measures now,
  - finds the tier the bill fell in and how many kWh it would take to drop a tier,
  - picks savings ideas from the measured load breakdown.

Privacy: the photo is used once, in memory, and never written to disk or to the
database. The model is told to ignore names, addresses and account numbers, and the
answer schema has no field for them. Only the numbers (kWh, days, JOD) are kept, so
"ليش الفاتورة هيك؟" can compare with them later.
"""

import base64
import binascii
import calendar
import datetime as dt
import time

from backend import billing, config, db, llm, state
from backend.actions import ActionError, require_site

# What the photo really is, from its first bytes (we do not trust the file name).
_MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]


def _media_type(raw: bytes) -> str | None:
    for magic, mt in _MAGIC:
        if raw.startswith(magic):
            return mt
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


# ---------------- what we ask the model ----------------

READ_SYSTEM = (
    "You read photos of Jordanian household electricity bills for WattWise, an energy-saving assistant. "
    "Copy only the numbers that are printed on the bill: consumption in kWh, the billing period, the amount in JOD, "
    "the tariff tiers (شرائح) with their kWh and price, and other charges. If a number is not clearly visible, use null. "
    "Never guess or invent a number. Never write the customer's name, address, account number, subscription number "
    "or meter serial number anywhere in your answer, even in the explanation. "
    "If the photo is not an electricity bill or is unreadable, say so with is_electricity_bill/readable = false. "
    "Write explanation_ar as 3 to 5 short sentences in simple, friendly Modern Standard Arabic (not dialect) for someone who never read a bill: "
    "what they consumed, which tier they reached and why the amount is what it is. Use only numbers from the bill."
)

READ_PROMPT = "اقرأ هذه الفاتورة واستخرج الأرقام كما هي مكتوبة، واشرحها بعربية بسيطة."

_NUM = {"type": ["number", "null"]}
_STR = {"type": ["string", "null"]}

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "is_electricity_bill": {"type": "boolean"},
        "readable": {"type": "boolean"},
        "kwh": _NUM,
        "period_from": {**_STR, "description": "YYYY-MM-DD"},
        "period_to": {**_STR, "description": "YYYY-MM-DD"},
        "days": {"type": ["integer", "null"]},
        "amount_jod": {**_NUM, "description": "Total to pay for this period, JOD"},
        "energy_jod": {**_NUM, "description": "Energy charge only (before fees), JOD"},
        "tariff_type": {"type": "string", "enum": ["sub", "unsub", "unknown"],
                        "description": "sub = مدعوم, unsub = غير مدعوم"},
        "tiers": {"type": "array", "items": {
            "type": "object",
            "properties": {"from_kwh": _NUM, "to_kwh": _NUM, "kwh": _NUM, "price_fils": _NUM, "jod": _NUM},
            "required": ["from_kwh", "to_kwh", "kwh", "price_fils", "jod"],
            "additionalProperties": False}},
        "other_charges": {"type": "array", "items": {
            "type": "object",
            "properties": {"name_ar": {"type": "string"}, "jod": _NUM},
            "required": ["name_ar", "jod"],
            "additionalProperties": False}},
        "explanation_ar": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["is_electricity_bill", "readable", "kwh", "period_from", "period_to", "days", "amount_jod",
                 "energy_jod", "tariff_type", "tiers", "other_charges", "explanation_ar", "confidence"],
    "additionalProperties": False,
}

NO_KEY_MSG = "قراءة الصورة غير متاحة. أدخل الأرقام يدويًا."


# ---------------- small helpers ----------------

def _num(v, lo=0.0, hi=1e6):
    """A clean positive number, or None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo < f < hi else None


def _days_between(a, b) -> int | None:
    try:
        d = (dt.date.fromisoformat(str(b)) - dt.date.fromisoformat(str(a))).days
    except ValueError:
        return None
    return d if 1 <= d <= 120 else None


# ---------------- the analysis the code does ----------------

def _analyze(conn, site: str, bill: dict, by: str, explanation: list[str]) -> dict:
    """Compare the bill with the tariff and the meter. Every number here is computed in code."""
    s = state.build(conn, site)
    tariff = config.load_tariff()
    b_now = s["bill"]
    ttype = bill.get("tariff_type") if bill.get("tariff_type") in tariff["types"] else b_now["type"]
    kwh, days, amount = bill.get("kwh"), bill.get("days"), bill.get("amount_jod")

    checks, ideas = [], []
    compare = {}
    if kwh:
        expected = round(billing.bill_for(kwh, tariff, ttype), 2)
        compare["tariff_energy_jod"] = expected
        label = tariff["types"][ttype]["label"]
        paid = bill.get("energy_jod") or amount
        if paid:
            diff = round(paid - expected, 2)
            if abs(diff) <= max(0.5, expected * 0.05):
                checks.append(f"حسبناها على تعرفة «{label}»: {kwh:g} ك.و.س = {expected:g} دينار طاقة. "
                              f"قريبة مما في الفاتورة ({paid:g}).")
            elif diff > 0:
                checks.append(f"على تعرفة «{label}» قيمة الطاقة وحدها = {expected:g} دينار، والفاتورة {paid:g}. "
                              f"الفرق {diff:g} دينار غالبًا رسوم أخرى (تلفزيون، نفايات، فلس الريف) أو تعرفة غير التي اخترتها.")
            else:
                checks.append(f"على تعرفة «{label}» يُفترض أن تكون {expected:g} دينار، والفاتورة أقل ({paid:g}). "
                              "ربما هناك دعم أو خصم، أو أن التعرفة في إعداداتنا تختلف عن تعرفتك.")

        # Which tier, and how far above the cheaper one?
        tiers = billing._tiers(tariff, ttype)
        prev_cap = 0.0
        for i, (cap, price) in enumerate(tiers):
            if kwh <= cap:
                fils = round(price * 1000)
                if i > 0:
                    over = round(kwh - prev_cap)
                    cheaper = round(tiers[i - 1][1] * 1000)
                    per_day = f" (≈ {over / days:.1f} يوميًا)" if days else ""
                    checks.append(f"وصلت إلى شريحة {fils} فلس، وحُسبت آخر {over} ك.و.س بالسعر الأغلى.")
                    ideas.append(f"لو خفّضت {over} ك.و.س شهريًا{per_day} تعود إلى شريحة {cheaper} فلس، "
                                 f"وتوفّر نحو {over * price:.2f} دينار (تقدير من التعرفة).")
                else:
                    checks.append(f"أنت في أرخص شريحة ({fils} فلس). كل ك.و.س توفّره يوفّر {fils} فلس.")
                break
            prev_cap = cap

    # Bill vs what the meter measures now (kWh per day).
    measured_per_day = round(b_now["projected_kwh"] / max(1, _days_in_month()), 2)
    if kwh and days:
        bill_per_day = round(kwh / days, 2)
        compare.update(bill_kwh_per_day=bill_per_day, measured_kwh_per_day=measured_per_day,
                       measured_source="المحاكي" if s["source"] == "simulator" else "العدّاد")
        src = "المحاكي (بيانات تجريبية)" if s["source"] == "simulator" else "العدّاد"
        if measured_per_day > 0:
            pct = round((measured_per_day - bill_per_day) / bill_per_day * 100)
            compare["diff_pct"] = pct
            trend = ("أعلى" if pct > 0 else "أقل") + f" بـ {abs(pct)}%"
            checks.append(f"في الفاتورة استهلكت {bill_per_day:g} ك.و.س يوميًا، والآن يقيس {src} {measured_per_day:g} يوميًا، "
                          f"أي {trend} من الفاتورة." if pct else
                          f"في الفاتورة {bill_per_day:g} ك.و.س يوميًا، والآن يقيس {src} الرقم نفسه تقريبًا.")

    if s["breakdown"]:
        top = s["breakdown"][0]
        ideas.append(f"أكبر بند الآن: {top['name']} (≈ {top['jod']:g} دينار حتى اليوم، تقدير من بصمات الأحمال). "
                     "ابدأ به.")
    ideas.append("أعطِ الوكيل هدفًا (مثلًا «أريد الفاتورة القادمة أقل من هذه»)، وسيسألك قبل أي إطفاء.")

    return {
        "by": by,
        "bill": {k: bill.get(k) for k in ("kwh", "days", "amount_jod", "energy_jod", "period_from", "period_to",
                                         "tiers", "other_charges", "confidence")} | {"tariff_type": ttype},
        "explanation": explanation,
        "checks": checks,
        "ideas": ideas[:3],
        "compare": compare,
        "note": ("الأرقام قرأها الذكاء الاصطناعي من الصورة، والمقارنات محسوبة برمجيًا. راجع الأرقام مع الفاتورة."
                 if by == "llm" else "الأرقام أدخلتها أنت، والمقارنات محسوبة برمجيًا من التعرفة والعدّاد."),
    }


def _days_in_month() -> int:
    t = time.localtime()
    return calendar.monthrange(t.tm_year, t.tm_mon)[1]


def _remember(conn, site: str, result: dict) -> None:
    """Keep only the numbers (never the photo) so "why is my bill like this?" can use them."""
    b = result["bill"]
    db.set_state(conn, f"last_bill:{site}", {"kwh": b["kwh"], "days": b["days"], "amount_jod": b["amount_jod"],
                                             "by": result["by"], "ts": time.time()})
    db.audit(conn, site, "T0", "agent", "bill_read",
             f"تحليل فاتورة ({'من صورة' if result['by'] == 'llm' else 'أرقام يدوية'}): "
             f"{b['kwh'] if b['kwh'] is not None else '—'} ك.و.س، {b['amount_jod'] if b['amount_jod'] is not None else '—'} دينار. "
             "لم تُحفظ الصورة.")


def last_bill(conn, site: str) -> dict | None:
    return db.get_state(conn, f"last_bill:{site}")


# ---------------- entry points ----------------

def status(conn) -> dict:
    """Can we read photos right now? (The apps show the manual form when not.)"""
    st = llm.status(conn)
    return {"photo": st["mode"] == "llm", "reason_ar": "" if st["mode"] == "llm" else NO_KEY_MSG}


def from_manual(conn, site: str, kwh, days, amount_jod) -> dict:
    require_site(site)
    kwh = _num(kwh, 0, 100_000)
    if kwh is None:
        raise ActionError("أدخل الكيلوواط ساعة (ك.و.س) كما هي في الفاتورة.")
    days_n = _num(days, 0, 121)
    bill = {"kwh": kwh, "days": round(days_n) if days_n else None, "amount_jod": _num(amount_jod, 0, 100_000),
            "energy_jod": None, "period_from": None, "period_to": None, "tiers": [], "other_charges": [],
            "confidence": None, "tariff_type": None}
    res = _analyze(conn, site, bill, "manual", [])
    _remember(conn, site, res)
    return res


def from_photo(conn, site: str, image_b64: str) -> dict:
    require_site(site)
    if "," in image_b64[:100] and image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]     # a data: URL from the browser
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ActionError("لم تصل الصورة بشكل صحيح. حاول مجددًا.")
    if len(raw) > config.BILL_PHOTO_MAX_BYTES:
        raise ActionError("الصورة كبيرة جدًا. صوّرها من مسافة أقرب أو اختر صورة أصغر.")
    media_type = _media_type(raw)
    if not media_type:
        raise ActionError("يجب أن يكون الملف صورة (JPG أو PNG أو WEBP).")

    provider = llm.get_provider()
    if provider is None or not llm.available(conn):
        return {"needs_manual": True, "message": NO_KEY_MSG if provider is None else
                llm.status(conn)["reason_ar"] + " أدخل أرقام الفاتورة يدويًا."}
    try:
        data, run = provider.read_image(READ_SYSTEM, READ_PROMPT, base64.b64encode(raw).decode(), media_type,
                                        READ_SCHEMA)
    except llm.ProviderError:
        llm.mark_down()
        return {"needs_manual": True, "message": "تعذّرت قراءة الصورة الآن (مشكلة اتصال أو خطأ). أدخل أرقام الفاتورة يدويًا."}
    finally:
        raw = image_b64 = None   # drop the photo from memory as soon as possible
    llm.add_spend(conn, run)

    if not data.get("is_electricity_bill") or not data.get("readable"):
        return {"needs_manual": True,
                "message": "الصورة غير واضحة أو ليست فاتورة كهرباء. صوّرها كاملة وبإضاءة جيدة، أو أدخل الأرقام يدويًا."}
    bill = {
        "kwh": _num(data.get("kwh"), 0, 100_000),
        "days": data.get("days") or _days_between(data.get("period_from"), data.get("period_to")),
        "amount_jod": _num(data.get("amount_jod"), 0, 100_000),
        "energy_jod": _num(data.get("energy_jod"), 0, 100_000),
        "period_from": data.get("period_from"), "period_to": data.get("period_to"),
        "tiers": data.get("tiers") or [], "other_charges": data.get("other_charges") or [],
        "confidence": data.get("confidence"),
        "tariff_type": data.get("tariff_type"),
    }
    if bill["days"] is not None and not 1 <= int(bill["days"]) <= 120:
        bill["days"] = None
    explanation = [str(x).strip()[:300] for x in data.get("explanation_ar") or [] if str(x).strip()][:5]
    res = _analyze(conn, site, bill, "llm", explanation)
    _remember(conn, site, res)
    return res
