"""Talking to WattWise in plain Arabic (rule-based, works offline, no API key).

- read_goal:      "بدي الفاتورة ما تتعدى ٢٥ دينار" -> target 25 JD
- parse_command:  "طفّي مكيّف النوم بعد نص ساعة" -> a list of actions, each already
                  checked by the Policy Guard (ok, or the Arabic reason it is refused)
- run_command:    runs the allowed actions AFTER the human pressed "yes"
- why_bill:       "why is my bill like this?" from the measured numbers
- weekly_report:  a plain-text report to download

Nothing here switches a device without the human's confirmation, and every
number comes from the code (meter, tariff, load signatures), never invented.
"""

import calendar
import re
import time

from backend import bill_reader, db, policy, schedules, state
from backend.actions import ActionError, human_toggle, require_site

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def norm(text: str) -> str:
    """Make Arabic easy to match: no diacritics, one form of alef/yaa/taa marbuta, Western digits."""
    t = re.sub(r"[ً-ٟـ]", "", text or "")      # tashkeel and tatweel
    t = re.sub(r"[أإآ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    t = t.replace("اضاءه", "اناره").replace("ضو", "اناره")
    return t.translate(_AR_DIGITS)


# ---------- goal in plain words ----------

_PERCENT = r"\s*(?:%|٪|بالميه|بالمئه|في الميه|في المئه|بالمائه)"


def read_goal(text: str) -> float | None:
    """The bill target in JD written inside the goal text, if any (5 to 1000).
    A percentage ("وفّر ٢٠٪") is not a bill target: see read_goal_percent."""
    t = norm(text)
    if read_goal_percent(text) is not None:
        t = re.sub(r"\d+(?:\.\d+)?" + _PERCENT, " ", t)
    m = re.search(r"\d+(?:\.\d+)?", t)
    if not m:
        return None
    value = float(m.group(0))
    return value if 5 <= value <= 1000 else None


def read_goal_percent(text: str) -> float | None:
    """'بدي أوفّر ٢٠٪ هالشهر' -> 20 (1 to 90 percent)."""
    m = re.search(r"(\d+(?:\.\d+)?)" + _PERCENT, norm(text))
    if not m:
        return None
    value = float(m.group(1))
    return value if 1 <= value <= 90 else None


def step_tag(step: str) -> str:
    """T1 for steps that switch something (need approval), T0 for automatic ones."""
    return "T1" if re.search(r"أسأل|اسأل|نسأل|موافق|اقتراح إطفاء|أقترح", step) else "T0"


# ---------- commands ----------

OFF_WORDS = r"(اطف|طف|سكر|وقف|اغلق|بطل)"
ON_WORDS = r"(شغل|افتح|اشعل|ولع|وصل)"
KIND_WORDS = {"ac": r"مكيف", "fan": r"مروح", "light": r"اناره|لمب", "heater": r"سخان", "tv": r"تلفزيون|شاشه",
              "washer": r"غسال", "pc": r"كمبيوتر"}


def _minutes_from(t: str) -> int | None:
    """'بعد 20 دقيقه' -> 20, 'بعد نص ساعه' -> 30, 'لمده ساعتين' -> 120."""
    m = re.search(r"(?:بعد|لمده|لمدة)\s+(\d+)\s*(دقيقه|دقايق|دقائق|د|ساعه|ساعات|س)\b", t)
    if m:
        return int(m.group(1)) * (60 if m.group(2).startswith("س") else 1)
    for words, n in ((r"نص\s+ساعه", 30), (r"ربع\s+ساعه", 15), (r"ساعتين", 120), (r"ساعه", 60)):
        if re.search(r"(?:بعد|لمده)\s+" + words, t):
            return n
    return None


def _schedule_from(t: str) -> tuple[str, str] | None:
    """'يشتغل من 6 لل 7' / 'من 05:30 الى 06:30' -> ('06:00', '07:00')."""
    m = re.search(r"من\s*(?:الساعه\s*)?(\d{1,2})(?::(\d{2}))?\s*(?:لل|ل|الى|حتى|لـ)\s*(?:الساعه\s*)?(\d{1,2})(?::(\d{2}))?", t)
    if not m:
        return None
    h1, m1, h2, m2 = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    return f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"


def _match_devices(t: str, devices: list[dict], rooms: dict[str, str]) -> list[dict]:
    """Which devices does the text mean? Full name first, then 'all lights', then kind + room."""
    def tokens(name):
        return [w[2:] if w.startswith("ال") else w for w in norm(name).split() if w not in ("غرفه",)]

    full = [d for d in devices if all(tok in t for tok in tokens(d["name"]))]
    if full:
        return full
    kinds = [k for k, rx in KIND_WORDS.items() if re.search(rx, t)]
    if not kinds:
        return []
    same_kind = [d for d in devices if d["kind"] in kinds]
    if "كل" in t.split():
        return same_kind
    in_room = [d for d in same_kind if any(tok in t for tok in tokens(rooms.get(d["room"], "")))]
    if in_room:
        return in_room
    return same_kind if len(same_kind) == 1 else []


def parse_command(conn, site: str, text: str) -> dict:
    """Understand a typed or spoken order. Returns items the UI shows for confirmation."""
    require_site(site)
    t = norm(text).strip()
    if not t:
        raise ActionError("اكتب أو احكي الأمر.")
    off, on = bool(re.search(OFF_WORDS, t)), bool(re.search(ON_WORDS, t))
    sched = _schedule_from(t)
    if not (off or on or sched):
        return {"reply": "", "clarify": "ما فهمت إذا بدك أطفي ولا أشغّل. جرّب: «طفّي مكيّف النوم».",
                "items": [], "by": "rules"}
    devices = db.devices(conn, site)
    rooms = {r["id"]: r["name"] for r in db.rooms(conn, site)}
    targets = _match_devices(t, devices, rooms)
    if not targets:
        return {"reply": "", "clarify": "ما عرفت أي جهاز بتقصد. اذكر اسمه زي ما هو بصفحة الأجهزة.",
                "items": [], "by": "rules"}
    minutes = _minutes_from(t)
    run_for = minutes is not None and bool(re.search(r"لمده|لمدة", t))
    items = []
    for d in targets[:8]:
        item = {"device_id": d["id"], "ok": True, "why": ""}
        if sched:
            item.update(action="schedule", on_time=sched[0], off_time=sched[1],
                        label=f"جدول {d['name']}: تشغيل {sched[0]} · إطفاء {sched[1]}")
            decision = policy.check_schedule(d, *sched)
        elif minutes is not None:
            turn_on = on and not off
            if run_for:
                item.update(action="run_for", minutes=minutes,
                            label=f"تشغيل {d['name']} لمدة {schedules.fmt_minutes(minutes)}")
            else:
                item.update(action="timer", minutes=minutes, turn_on=turn_on,
                            label=f"{'تشغيل' if turn_on else 'إطفاء'} {d['name']} بعد {schedules.fmt_minutes(minutes)}")
            decision = policy.check_timer(d, minutes)
        else:
            turn_on = on and not off
            item.update(action="on" if turn_on else "off", label=f"{'تشغيل' if turn_on else 'إطفاء'} {d['name']}")
            decision = policy.check_switch(d, turn_on, policy.HUMAN, None, plug=db.plug(conn, site, d["id"]))
            if decision.allowed and d["sensitive"] and not turn_on:
                decision = policy.Decision(False, "sensitive_device",
                                           f"{d['name']} بيقطع تطبيق الموافقة. طفّيه من صفحة الأجهزة بتأكيد إضافي.")
            elif decision.allowed and bool(d["is_on"]) == turn_on:
                decision = policy.Decision(False, "no_change", "هو أصلاً شغّال." if turn_on else "هو أصلاً مطفي.")
        if not decision.allowed:
            item["ok"], item["why"] = False, decision.reason_ar
        items.append(item)
    reply = "فهمت أمرك. أكّد قبل ما أنفّذ:" if any(i["ok"] for i in items) else "ما في إشي بقدر أنفّذه من هالأمر:"
    return {"reply": reply, "clarify": None, "items": items, "by": "rules"}


def run_command(conn, site: str, text: str) -> dict:
    """The human pressed "yes": parse the SAME text again on the server and run the allowed items."""
    parsed = parse_command(conn, site, text)
    done = []
    for i in parsed["items"]:
        if not i["ok"]:
            continue
        try:
            if i["action"] in ("on", "off"):
                human_toggle(conn, site, i["device_id"], i["action"] == "on")
            elif i["action"] == "timer":
                schedules.add_timer(conn, site, i["device_id"], i["minutes"], i["turn_on"])
            elif i["action"] == "run_for":
                schedules.add_timer(conn, site, i["device_id"], i["minutes"], False, run_now=True)
            elif i["action"] == "schedule":
                schedules.add_schedule(conn, site, i["device_id"], i["on_time"], i["off_time"], source="command")
            done.append(i["label"])
        except ActionError as e:
            i["ok"], i["why"] = False, str(e)
    if done:
        db.audit(conn, site, "MANUAL", "human", "voice_command",
                 f"أمر بالكلام: «{text.strip()[:70]}» ← {'، '.join(done)}. أكّدته إنت، وحارس السياسات وافق.")
    return {"done": done, "items": parsed["items"]}


# ---------- why is my bill like this? ----------

def why_bill(conn, site: str) -> dict:
    """Explain the bill from measured data only. Shares are estimates from load signatures."""
    s = state.build(conn, site)
    b, goal = s["bill"], (s.get("goal") or {}).get("bill_target_jd")
    proj = b["bill_projected"]
    if goal:
        head = (f"متوقّع آخر الشهر {proj:g} دينار، وهدفك {goal:g}. " +
                ("لازم ننزل شوي." if proj > goal else "ماشيين صح."))
    else:
        head = f"متوقّع آخر الشهر {proj:g} دينار. أعطِ الوكيل هدف عشان نقارن فيه."
    causes = []
    if s["breakdown"]:
        top = s["breakdown"][0]
        causes.append({"what": f"{top['name']} أكبر بند بالفاتورة",
                       "evidence": f"تقريباً {top['jod']:g} دينار لحد اليوم (تقدير من بصمات الأحمال على العدّاد)."})
    fils = round(b["price_jod_per_kwh"] * 1000)
    causes.append({"what": f"إنت بشريحة {fils} فلس للكيلوواط ساعة",
                   "evidence": f"استهلاكك لحد اليوم {b['kwh_now']:g} ك.و.س. {b['message']}"})
    on_now = sorted((d for d in s["devices"] if d["is_on"] and d["tier"] == "T1"), key=lambda d: -d["est_w"])
    if on_now:
        d = on_now[0]
        causes.append({"what": f"أكبر جهاز شغّال هلأ: {d['name']}",
                       "evidence": f"بصمته ≈ {d['est_w']} واط = {d['est_w'] / 1000 * b['price_jod_per_kwh']:.3f} دينار بالساعة."})
    last = bill_reader.last_bill(conn, site)
    if last and last.get("kwh") and last.get("days"):
        bill_day = last["kwh"] / last["days"]
        now_day = b["projected_kwh"] / max(1, calendar.monthrange(*time.localtime()[:2])[1])
        if now_day > 0:
            pct = round((now_day - bill_day) / bill_day * 100)
            causes.insert(1, {"what": "مقارنة مع فاتورتك الأخيرة",
                              "evidence": f"الفاتورة: {bill_day:.1f} ك.و.س باليوم. هلأ: {now_day:.1f} باليوم "
                                          f"({'أعلى' if pct > 0 else 'أقل'} بـ {abs(pct)}%)."})
    heater = next((d for d in s["devices"] if d["kind"] == "heater"), None)
    has_heater_plan = heater and any(r["device_id"] == heater["id"] for r in schedules.listing(conn, site)["schedules"])
    if heater and not has_heater_plan:
        action = "جرّب «اقترحلي جدول للسخّان»: بيسخّن قبل الحمّام بس بدل ما يضل شغّال."
    else:
        action = "خلّي الوكيل يراقب، وبنسألك قبل أي إطفاء."
    return {"headline": head, "causes": causes[:4], "action": action, "by": "rules",
            "note": "تحليل بالقواعد من القياسات. النسب تقديرية من بصمات الأحمال."}


# ---------- weekly report (plain text, for download) ----------

def weekly_report(conn, site: str) -> str:
    s = state.build(conn, site)
    b, sv = s["bill"], s["savings"]
    goal = (s.get("goal") or {}).get("bill_target_jd")
    lines = [
        f"WattWise — التقرير الأسبوعي · {s['site_name']}",
        f"التاريخ: {time.strftime('%Y-%m-%d')}",
        "(بيانات المحاكي)" if s["source"] == "simulator" else "(قياسات العدّاد الحقيقي)",
        "",
        f"الاستهلاك لحد اليوم: {b['kwh_now']:g} ك.و.س",
        f"الفاتورة لحد اليوم: {b['bill_now']:g} دينار (شريحة {round(b['price_jod_per_kwh'] * 1000)} فلس)",
        f"المتوقّع آخر الشهر: {b['bill_projected']:g} دينار" + (f" · الهدف: {goal:g} دينار" if goal else ""),
    ]
    if sv["kwh"] > 0:
        co2 = f" = {sv['co2_kg']:g} كغ CO2" if sv.get("co2_kg") is not None else ""
        lines.append(f"التوفير المُقاس: {sv['kwh']:g} ك.و.س = {sv['jod']:g} دينار{co2}")
    else:
        lines.append("التوفير المُقاس: لسا ما في توفير مُقاس هالفترة.")
    lines += ["(كل الأرقام محسوبة بالكود من القياسات والتعرفة.)", "", "وين بتروح الفلوس (تقدير):"]
    lines += [f"- {x['name']}: {x['jod']:g} دينار" for x in s["breakdown"]] or ["- لسا ما في بيانات كفاية."]
    sch = schedules.listing(conn, site)["schedules"]
    if sch:
        lines += ["", "الجداول الشغّالة:"]
        lines += [f"- {r['device_name']}: {r['on_time'] or '—'} ← {r['off_time'] or '—'}"
                  + ("" if r["enabled"] else " (موقوف)") for r in sch]
    log = db.rows(conn.execute("SELECT clock, tier, message FROM audit_log WHERE site=? ORDER BY id DESC LIMIT 10",
                               (site,)))
    lines += ["", "آخر القرارات:"] + [f"- {e['clock']} [{e['tier']}] {e['message']}" for e in log]
    lines += ["", "اقتراح للأسبوع الجاي (بيحتاج موافقتك): " + why_bill(conn, site)["action"]]
    return "\n".join(lines) + "\n"
