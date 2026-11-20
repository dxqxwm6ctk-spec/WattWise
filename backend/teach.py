"""Teach mode: the AI learns a room's appliances by talking with the user.

The story:
  1. The user clamps the PZEM on one room's breaker and presses "teach me this room".
  2. The AI asks: switch the devices on one by one, 5 seconds apart.
  3. backend/nilm.py finds each step (watts + power factor). Here each step
     becomes a "candidate" with a guess: "about 62 W, pf 0.58: probably a laptop".
  4. When the meter is quiet, the AI sums up and asks: "is this right?"
  5. The user answers in normal Arabic: "صح", or "الأول لابتوب، الثاني ضو المكتب",
     or "الثالث تجاهله". The AI repeats what it understood.
  6. It asks for permission. Only if the user says yes are the fingerprints
     saved for that room. "No" means nothing is kept.
  7. From then on nilm.py recognises those devices on the meter, and a step that
     matches nothing raises "unknown device" and the AI asks what it is.

Understanding the reply: rules in plain Python (works with no internet). When an
LLM is configured and within budget, it reads the reply first and the rules
are the fallback. The LLM only reads the text; saving still needs the user's
"yes", and nothing here switches a device.
"""

import json
import re
import time

from backend import actions, config, db, llm, nilm

QUIET_S = 12          # meter quiet this long after the last new device: sum up
NUDGE_S = 90          # nothing seen this long after start: remind the user what to do


# ---------------- small helpers ----------------

def session(conn, site: str) -> dict | None:
    return db.get_state(conn, f"teach:{site}")


def _set_session(conn, site: str, s: dict | None) -> None:
    db.set_state(conn, f"teach:{site}", s)


def _ctx(conn, site: str) -> dict | None:
    return db.get_state(conn, f"chat_ctx:{site}")


def _set_ctx(conn, site: str, ctx: dict | None) -> None:
    db.set_state(conn, f"chat_ctx:{site}", ctx)


def _say(conn, site: str, role: str, text: str, data: dict | None = None) -> None:
    conn.execute("INSERT INTO chat_messages (site, ts, role, text, data) VALUES (?,?,?,?,?)",
                 (site, time.time(), role, text, json.dumps(data or {}, ensure_ascii=False)))


def say_ai(conn, site: str, text: str, data: dict | None = None) -> None:
    _say(conn, site, "ai", text, data)


def messages(conn, site: str, limit: int = 40) -> list[dict]:
    rows = db.rows(conn.execute(
        "SELECT id, ts, role, text FROM chat_messages WHERE site=? ORDER BY id DESC LIMIT ?", (site, limit)))
    rows.reverse()
    return rows


def _count(n: int) -> str:
    return {1: "جهاز واحد", 2: "جهازين"}.get(n, f"{n} أجهزة")


def _li(name: str) -> str:
    """Arabic "for <room>": لـ + المطبخ = للمطبخ."""
    return "لل" + name[2:] if name.startswith("ال") else "ل" + name


def _pf_txt(pf) -> str:
    return f"، معامل القدرة ≈ {pf:.2f}" if pf is not None else ""


# ---------------- Arabic text rules ----------------

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
# One character to one character, so positions in the normalised text match the original.
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": " "})


def norm(text: str) -> str:
    return text.translate(_DIGITS).translate(_LETTERS).lower()


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", norm(text))


YES = {"صح", "صحيح", "اه", "اي", "ايوا", "ايوه", "نعم", "تمام", "مزبوط", "اكيد", "yes", "ok", "okay",
       "اوكي", "احفظ", "احفظهم", "احفظه", "احفظها", "موافق", "طيب", "يلا", "ماشي", "زابط"}
NO = {"لا", "لاء", "no", "بلاش", "الغي", "لاتحفظ"}
DROP_WORDS = ("تجاهل", "احذف", "شيل", "انسى", "انساه", "مش جهاز", "غلط", "مش مهم", "خليه", "طنش")


def is_no(text: str) -> bool:
    w = _words(text)
    t = norm(text)
    return bool(w) and (w[0] in NO or "ما بدي" in t or "لا تحفظ" in t or "مش موافق" in t)


def is_yes(text: str) -> bool:
    w = _words(text)
    return bool(w) and not is_no(text) and w[0] in YES and len(w) <= 4


def is_drop(text: str) -> bool:
    t = norm(text)
    return any(d in t for d in DROP_WORDS)


# Device names -> kind (for safety tiers and icons).
KIND_WORDS = [
    (r"لابتوب|كمبيوتر|حاسوب|حاسب|laptop|pc\b", "pc"),
    (r"ضو|ضوء|لمبه|انار|ليد|led|اباجور|ابجور|سبوت|نيون", "light"),
    (r"مروح|fan", "fan"),
    (r"تلفزيون|تلفاز|شاشه|tv", "tv"),
    (r"راوتر|مودم|router", "router"),
    (r"شاحن|charger", "other"),
    (r"مكيف", "ac"),
    (r"سخان|غلاي|مكوي|مكواه|دفاي|صوبه|فرن|ميكرو|كيتل", "heater"),
    (r"ثلاج|فريزر|براد", "fridge"),
    (r"غسال|جلاي", "washer"),
    (r"طبي|اكسجين|اوكسجين|medical", "medical"),
    (r"انذار|حريق", "fire_alarm"),
]


def kind_from_name(name: str, fallback: str = "other") -> str:
    t = norm(name)
    for pattern, kind in KIND_WORDS:
        if re.search(pattern, t):
            return kind
    return fallback


_ORD = {"اول": 1, "ثاني": 2, "ثانيه": 2, "ثالث": 3, "ثالثه": 3, "رابع": 4, "رابعه": 4,
        "خامس": 5, "خامسه": 5, "سادس": 6, "سادسه": 6}
_REF = re.compile(r"(?<!\w)و?(?:ال)?(اول|ثانيه|ثاني|ثالثه|ثالث|رابعه|رابع|خامسه|خامس|سادسه|سادس)(?!\w)"
                  r"|(\d+(?:\.\d+)?)\s*(واط|w(?!\w))?")
_FILLER = {"هو", "هي", "هاد", "هاي", "هذا", "هذه", "عبارة", "عباره", "عن", "يعني", "و", "بس", "كمان",
           "اسمه", "اسمها", "رقم", "الجهاز", "جهاز", "واط", "w", "صح", "لا", "لاء", "هيك", "تبعت", "تبع"}


def _clean_label(original: str) -> str:
    n = norm(original)
    # "مش لمبة" means "not a lamp": remove that part, keep the rest ("مش لمبة، مروحة" -> "مروحة").
    for m in reversed(list(re.finditer(r"(?<!\w)مش\s+(?:[^،,؛.]+[،,؛.]|\w+)", n))):
        original, n = original[:m.start()] + original[m.end():], n[:m.start()] + n[m.end():]
    words = original.replace("،", " ").replace(",", " ").replace(":", " ").replace("=", " ") \
        .replace("-", " ").replace("؛", " ").replace(".", " ").split()
    while words and norm(words[0]) in _FILLER:
        words.pop(0)
    while words and norm(words[-1]) in _FILLER:
        words.pop()
    return " ".join(words)[:40]


def parse_labels(text: str, candidates: list[dict]) -> dict[int, dict]:
    """Rule-based reading of "الأول لابتوب، الثاني ضو المكتب، الثالث تجاهله".

    Returns {candidate number (1-based): {"name": str} or {"drop": True}}.
    A number followed by "واط" (or bigger than the list) means watts: the closest candidate.
    """
    n_text = norm(text)
    refs = []
    for m in _REF.finditer(n_text):
        if m.group(1):
            refs.append((m.start(), m.end(), _ORD[m.group(1)]))
            continue
        value = float(m.group(2))
        if m.group(3) or value > len(candidates) or value != int(value):
            best = min(range(len(candidates)), key=lambda i: abs(candidates[i]["w"] - value), default=None)
            if best is not None and abs(candidates[best]["w"] - value) <= max(3, 0.35 * candidates[best]["w"]):
                refs.append((m.start(), m.end(), best + 1))
        else:
            refs.append((m.start(), m.end(), int(value)))
    out: dict[int, dict] = {}
    if not refs:
        if len(candidates) == 1 and not is_yes(text):
            out[1] = {"drop": True} if is_drop(text) else {"name": _clean_label(text)}
        return {k: v for k, v in out.items() if v.get("drop") or v.get("name")}
    for i, (_, end, n) in enumerate(refs):
        if not 1 <= n <= len(candidates):
            continue
        stop = refs[i + 1][0] if i + 1 < len(refs) else len(text)
        segment = text[end:stop]
        if is_drop(segment):
            out[n] = {"drop": True}
        else:
            label = _clean_label(segment)
            if label:
                out[n] = {"name": label}
            elif "مش" in norm(segment):      # "الثالث مش لمبة": the guess is wrong, no new name given
                out[n] = {"name": f"جهاز ≈ {round(candidates[n - 1]['w'])} واط"}
    return out


def find_room(conn, site: str, text: str) -> tuple[str | None, str]:
    """Find a room name in the text. Returns (room id or None, text without the room part)."""
    n_text = norm(text)
    for r in db.rooms(conn, site):
        core = norm(r["name"])
        core = core[2:] if core.startswith("ال") else core
        m = re.search(r"(?:(?<!\w)في\s+|(?<!\w)عند\s+|(?<!\w)ب\s*)?(?:ال)?" + re.escape(core), n_text)
        if m:
            return r["id"], text[:m.start()] + text[m.end():]
    return None, text


# ---------------- teach session ----------------

def start(conn, site: str, room: str) -> dict:
    actions.require_site(site)
    if not db.one(conn.execute("SELECT 1 AS x FROM rooms WHERE site=? AND id=?", (site, room))):
        raise actions.ActionError("الغرفة مش معروفة.")
    if db.get_state(conn, f"learn:{site}"):
        raise actions.ActionError("خلّص إضافة الجهاز الجديد أول.")
    now = time.time()
    _set_session(conn, site, {"room": room, "status": "listening", "started_ts": now, "last_event_ts": now,
                              "base_w": None, "candidates": [], "nudged": False})
    _set_ctx(conn, site, None)
    db.set_state(conn, f"meter_room:{site}", room)   # the PZEM stays on this breaker afterwards
    nilm.reset_buffers(site)
    cfg = config.load_sites()[site]
    rname = nilm.room_name(conn, site, room)
    if cfg["source"] == "simulator":
        where = (f"(بالمحاكي: ركّبنا العدّاد على قاطع {rname}، والمحاكي رح يمثّل إنك عم تشغّل "
                 "الأجهزة واحد واحد. كل البيانات تركيبية.)")
    elif len(cfg["rooms"]) == 1:
        where = f"العدّاد (PZEM) أصلًا على قاطع {rname}."
    else:
        where = f"تأكّد إنه الكهربائي ركّب العدّاد على قاطع {rname}."
    say_ai(conn, site,
           f"تمام! خلّيني أتعلّم أجهزة {rname}. {where}\n"
           "١) طفّي الأجهزة اللي بدك أتعرّف عليها بهالغرفة.\n"
           "٢) شغّلهم واحد واحد، واستنّى ٥ ثواني بين كل جهاز والثاني.\n"
           "٣) أنا بسمع للعدّاد، ولما يهدى بلخّصلك شو شفت وبسألك.")
    db.audit(conn, site, "T0", "human", "teach_start", f"بلّش تعليم أجهزة {rname} (وضع التعلّم).")
    return state(conn, site)


def add_candidate(conn, site: str, ev: dict) -> None:
    """A step up in the teach room that matches nothing known."""
    t = session(conn, site)
    if not t:
        return
    if t["base_w"] is None:
        t["base_w"] = ev["before_w"]
    t["last_event_ts"] = ev["ts"]
    for c in t["candidates"]:
        if nilm.matches(ev["dp"], ev["pf"], c["w"], c["pf"], ev["noisy"]):
            c["count"] += 1
            c["w"] = round((c["w"] * (c["count"] - 1) + ev["dp"]) / c["count"], 1)
            _set_session(conn, site, t)
            return
    g = nilm.guess(ev["dp"], ev["pf"], ev["pf_quality"])
    pf = ev["pf"] if ev["pf_quality"] == "ok" else None   # a weak pf is not shown or saved
    t["candidates"].append({"w": round(ev["dp"], 1), "pf": pf, "pf_quality": ev["pf_quality"], "count": 1,
                            "guess": g, "name": None, "kind": g[0]["kind"], "drop": False})
    _set_session(conn, site, t)
    say_ai(conn, site, f"شفت جهاز انشغل: +{round(ev['dp'])} واط{_pf_txt(pf)}. غالبًا {g[0]['label']}.")


def note_recognised(conn, site: str, fp: dict, ev: dict) -> None:
    t = session(conn, site)
    if t and t["status"] == "listening" and t["room"] == fp["room"]:
        t["last_event_ts"] = ev["ts"]
        t["recognised"] = t.get("recognised", 0) + 1
        _set_session(conn, site, t)
        say_ai(conn, site, f"هاد بعرفه: {fp['name']} (≈ {round(abs(ev['dp']))} واط) ✓")


def check(conn, site: str, now: float) -> None:
    """Called for every reading: sum up when the meter has been quiet."""
    t = session(conn, site)
    if not t or t["status"] != "listening":
        return
    if t["candidates"] and now - t["last_event_ts"] > QUIET_S:
        _summarize(conn, site, t)
    elif not t["candidates"] and t.get("recognised") and now - t["last_event_ts"] > QUIET_S:
        say_ai(conn, site, "كل الأجهزة اللي شفتها بعرفها من قبل ✓ ما في إشي جديد أحفظه، فسكّرت وضع التعلّم.")
        _end(conn, site)
    elif not t["candidates"] and not t["nudged"] and now - t["started_ts"] > NUDGE_S:
        t["nudged"] = True
        _set_session(conn, site, t)
        say_ai(conn, site, "لسّا ما شفت ولا جهاز جديد. شغّل جهاز واستنّى ٥ ثواني، أو اكبس «خلصت» إذا بدك نوقف.")


def _guess_text(c: dict) -> str:
    g = c["guess"]
    txt = g[0]["label"]
    if len(g) > 1 and g[1]["confidence"] >= 0.8 * g[0]["confidence"]:
        txt += f" أو {g[1]['label']}"
    return txt


def _summarize(conn, site: str, t: dict) -> None:
    room = t["room"]
    lines = [f"{i}) ≈ {round(c['w'])} واط{_pf_txt(c['pf'])} ← غالبًا {_guess_text(c)}"
             for i, c in enumerate(t["candidates"], 1)]
    known = [d for d in db.devices(conn, site) if d["room"] == room and d["is_on"]]
    base = ""
    if t["base_w"] is not None and t["base_w"] > 3:
        base = f"\nوكان في ≈ {round(t['base_w'])} واط شغّالة من قبل ما تبلّش"
        if known:
            base += " (الأجهزة المسجّلة: " + "، ".join(f"{d['name']} {round(d['signature_w'])}" for d in known) + ")"
        base += "."
    say_ai(conn, site,
           f"ب{nilm.room_name(conn, site, room)} شفت {_count(len(lines))}:\n" + "\n".join(lines) + base +
           "\nصح هيك؟ اكتب «صح»، أو صحّحلي مثلًا: «الأول لابتوب، الثاني ضو المكتب»، أو «الثالث تجاهله».",
           {"candidates": t["candidates"]})
    t["status"] = "asking"
    _set_session(conn, site, t)
    _set_ctx(conn, site, {"type": "teach_confirm"})


def finish(conn, site: str) -> dict:
    """The user pressed "done"."""
    t = session(conn, site)
    if t and t["status"] == "listening":
        if t["candidates"]:
            _summarize(conn, site, t)
        else:
            say_ai(conn, site, "ما شفت أجهزة جديدة، فسكّرت وضع التعلّم. ما انحفظ إشي.")
            _end(conn, site)
    return state(conn, site)


def cancel(conn, site: str) -> dict:
    if session(conn, site) or _ctx(conn, site):
        say_ai(conn, site, "وقّفت. ما حفظت إشي، والقياسات انمسحت.")
        db.audit(conn, site, "T0", "human", "teach_cancel", "توقّف وضع التعلّم بدون حفظ.")
    _end(conn, site)
    return state(conn, site)


def _end(conn, site: str) -> None:
    _set_session(conn, site, None)
    _set_ctx(conn, site, None)
    # An unknown device that showed up while we were busy: ask about it now.
    waiting = nilm.unknowns(conn, site)
    if waiting and waiting[-1]["status"] == "open":
        ask_about_unknown(conn, site, waiting[-1])


def _final_list(t: dict) -> list[dict]:
    out = []
    for c in t["candidates"]:
        if c["drop"]:
            continue
        name = c["name"] or c["guess"][0]["label"]
        out.append({**c, "name": name, "kind": kind_from_name(name, c["guess"][0]["kind"])})
    return out


def _ask_save(conn, site: str, t: dict) -> None:
    items = _final_list(t)
    if not items:
        say_ai(conn, site, "تمام، ما ضل إشي أحفظه. سكّرت وضع التعلّم.")
        _end(conn, site)
        return
    lines = []
    for c in items:
        line = f"• {c['name']} ≈ {round(c['w'])} واط{_pf_txt(c['pf'])}"
        if c["kind"] in config.FORBIDDEN_KINDS:
            line += " (جهاز حسّاس: بتعرّف عليه بس، وما بقترح أطفيه أبدًا)"
        lines.append(line)
    say_ai(conn, site, "هيك فهمت:\n" + "\n".join(lines) +
           f"\nبدّك أحفظ بصماتهم {_li(nilm.room_name(conn, site, t['room']))} عشان أتعرّف عليهم بعدين؟ (احفظ / لا)")
    t["status"] = "saving"
    _set_session(conn, site, t)
    _set_ctx(conn, site, {"type": "teach_save"})


def _save_all(conn, site: str, t: dict) -> None:
    items = _final_list(t)
    on = db.get_state(conn, f"nilm_on:{site}") or {}
    for c in items:
        fid = nilm.save_fingerprint(conn, site, t["room"], c["name"], c["kind"], c["w"], c["pf"], c["count"])
        on[str(fid)] = {"since": time.time(), "tipped": False}   # the user just switched them on
    db.set_state(conn, f"nilm_on:{site}", on)
    rname = nilm.room_name(conn, site, t["room"])
    db.audit(conn, site, "T0", "human", "fingerprints_saved",
             f"انحفظت {len(items)} بصمات {_li(rname)} بموافقة المستخدم: " + "، ".join(c["name"] for c in items),
             {"items": [{"name": c["name"], "w": c["w"], "pf": c["pf"]} for c in items]})
    say_ai(conn, site, f"حفظتهم ✓ من هلأ لما ينشغل أو ينطفي واحد منهم ب{rname} بعرفه، "
                       "وإذا طلع جهاز ما إله بصمة بنبّهك وبسألك عنه.")


# ---------------- unknown devices ----------------

def ask_about_unknown(conn, site: str, u: dict) -> None:
    where = f"ب{nilm.room_name(conn, site, u['room'])}" if u["room"] else "(على العدّاد الرئيسي، فالغرفة مش معروفة)"
    busy = (_ctx(conn, site) or {}).get("type", "").startswith("teach")
    text = (f"⚠️ في جهاز مجهول بيسحب ≈ {u['watts']} واط {where}{_pf_txt(u['pf'])}. ما إله بصمة محفوظة. "
            f"غالبًا: {u['guess'][0]['label']}.")
    if busy:
        say_ai(conn, site, text + " (بنرجعله بعد ما نخلّص التعلّم.)")
        return
    say_ai(conn, site, text + "\nشو هاد الجهاز؟ اكتبلي اسمه (ووين هو إذا بتعرف)، أو اكتب «تجاهل».",
           {"unknown": u})
    _set_ctx(conn, site, {"type": "label", "unknown": u})


def _label_reply(conn, site: str, ctx: dict, text: str, reading: dict | None) -> None:
    u = ctx["unknown"]
    if (reading and reading["intent"] in ("ignore", "no")) or (not reading and (is_drop(text) or is_no(text))):
        nilm.set_unknown_status(conn, site, u["id"], "dismissed")
        say_ai(conn, site, "تمام، تجاهلته. ما حفظت إشي.")
        _set_ctx(conn, site, None)
        return
    if reading:
        room = reading.get("room_id") or None
        name = (reading.get("items") or [{}])[0].get("name", "").strip()
    else:
        room, rest = find_room(conn, site, text)
        name = _clean_label(rest)
    room = room or u["room"]
    if not name:
        say_ai(conn, site, "شو اسم الجهاز؟ مثلًا: «مكوى» أو «سخّان صغير بالمطبخ».")
        return
    nxt = {"type": "label_save" if room else "label_room", "unknown": u, "name": name,
           "kind": kind_from_name(name, u["guess"][0]["kind"]), "room": room}
    _set_ctx(conn, site, nxt)
    if not room:
        say_ai(conn, site, f"تمام، «{name}». بأي غرفة هو؟")
    else:
        _ask_label_save(conn, site, nxt)


def _ask_label_save(conn, site: str, ctx: dict) -> None:
    u = ctx["unknown"]
    note = " (جهاز حسّاس: بتعرّف عليه بس، وما بقترح أطفيه أبدًا)" if ctx["kind"] in config.FORBIDDEN_KINDS else ""
    say_ai(conn, site, f"بدّك أحفظ بصمة «{ctx['name']}» (≈ {u['watts']} واط{_pf_txt(u['pf'])}) "
                       f"ب{nilm.room_name(conn, site, ctx['room'])}؟{note} (احفظ / لا)")


def _label_save_reply(conn, site: str, ctx: dict, text: str) -> None:
    u = ctx["unknown"]
    if is_yes(text):
        fid = nilm.save_fingerprint(conn, site, ctx["room"], ctx["name"], ctx["kind"], u["watts"], u["pf"],
                                    source="unknown")
        on = db.get_state(conn, f"nilm_on:{site}") or {}
        on[str(fid)] = {"since": time.time(), "tipped": False}
        db.set_state(conn, f"nilm_on:{site}", on)
        nilm.set_unknown_status(conn, site, u["id"], "labeled")
        rname = nilm.room_name(conn, site, ctx["room"])
        db.audit(conn, site, "T0", "human", "fingerprints_saved",
                 f"انحفظت بصمة «{ctx['name']}» (≈ {u['watts']} واط) {_li(rname)} بموافقة المستخدم.")
        say_ai(conn, site, f"حفظتها ✓ المرة الجاية بعرف «{ctx['name']}» لحالي.")
        _set_ctx(conn, site, None)
    elif is_no(text):
        nilm.set_unknown_status(conn, site, u["id"], "dismissed")
        say_ai(conn, site, "تمام، ما حفظت إشي.")
        _set_ctx(conn, site, None)
    else:
        say_ai(conn, site, "جاوبني بـ «احفظ» أو «لا».")


# ---------------- the user's reply ----------------

def _llm_read(conn, site: str, ctx: dict, text: str) -> dict | None:
    """Let the LLM read the reply when it is available. Any problem: None (rules take over)."""
    if not llm.available(conn):
        return None
    if ctx["type"] == "teach_confirm":
        cands = [{"n": i, "watts": round(c["w"]), "pf": c["pf"], "guess": c["guess"][0]["label"]}
                 for i, c in enumerate(session(conn, site)["candidates"], 1)]
    else:
        u = ctx["unknown"]
        cands = [{"n": 1, "watts": u["watts"], "pf": u["pf"], "guess": u["guess"][0]["label"]}]
    rooms = [{"id": r["id"], "name": r["name"]} for r in db.rooms(conn, site)]
    try:
        reading, result = llm.read_reply(llm.get_provider(), ctx["type"], cands, rooms, text)
    except llm.ProviderError:
        llm.mark_down()
        return None
    except Exception:  # never let the LLM break the conversation
        llm.mark_down()
        return None
    llm.add_spend(conn, result)
    return reading


def say(conn, site: str, text: str) -> dict:
    actions.require_site(site)
    text = text.strip()[:300]
    if not text:
        raise actions.ActionError("اكتب إشي.")
    ctx = _ctx(conn, site)
    # Read first (the LLM can take a few seconds), write after.
    reading = _llm_read(conn, site, ctx, text) if ctx and ctx["type"] in ("teach_confirm", "label") else None
    _say(conn, site, "user", text)

    if not ctx:
        m = re.search(r"علم|تعلم|تعرف|اتعرف", norm(text))
        room, _ = find_room(conn, site, text)
        if m and room:
            return start(conn, site, room)
        say_ai(conn, site, "أنا هون بتعلّم أجهزة الغرف. اختار غرفة واكبس «علّمني»، "
                           "أو اكتب مثلًا: «تعرّف على أجهزة غرفة الأولاد».")
    elif ctx["type"] == "teach_confirm":
        _confirm_reply(conn, site, text, reading)
    elif ctx["type"] == "teach_save":
        t = session(conn, site)
        if is_yes(text):
            _save_all(conn, site, t)
            _end(conn, site)
        elif is_no(text):
            say_ai(conn, site, "تمام، ما حفظت إشي، والقياسات انمسحت.")
            db.audit(conn, site, "T0", "human", "teach_declined", "المستخدم رفض حفظ البصمات. ما انحفظ إشي.")
            _end(conn, site)
        else:
            say_ai(conn, site, "جاوبني بـ «احفظ» أو «لا».")
    elif ctx["type"] == "label":
        _label_reply(conn, site, ctx, text, reading)
    elif ctx["type"] == "label_room":
        room, _ = find_room(conn, site, text)
        if not room:
            say_ai(conn, site, "ما عرفت الغرفة. اكتب اسمها مثل: " + "، ".join(r["name"] for r in db.rooms(conn, site)[:3]))
        else:
            ctx["room"] = room
            ctx["type"] = "label_save"
            _set_ctx(conn, site, ctx)
            _ask_label_save(conn, site, ctx)
    elif ctx["type"] == "label_save":
        _label_save_reply(conn, site, ctx, text)
    return state(conn, site)


def _confirm_reply(conn, site: str, text: str, reading: dict | None) -> None:
    t = session(conn, site)
    cands = t["candidates"]
    if reading:
        if reading["intent"] in ("yes", "labels", "ignore"):
            for it in reading.get("items", []):
                n = it.get("n", 0)
                if 1 <= n <= len(cands):
                    if it.get("ignore"):
                        cands[n - 1]["drop"] = True
                    elif it.get("name", "").strip():
                        cands[n - 1]["name"] = it["name"].strip()[:40]
            _set_session(conn, site, t)
            _ask_save(conn, site, t)
            return
        if reading["intent"] == "no":
            say_ai(conn, site, "طيب، صحّحلي: مين الأول ومين الثاني؟ مثلًا: «الأول مروحة، الثاني ضو صغير».")
            return
    if is_yes(text):
        _ask_save(conn, site, t)
        return
    labels = parse_labels(text, cands)
    if not labels:
        if is_no(text):
            say_ai(conn, site, "طيب، صحّحلي: مين الأول ومين الثاني؟ مثلًا: «الأول مروحة، الثاني ضو صغير».")
        else:
            say_ai(conn, site, "ما فهمت عليك 🙏 اكتب مثلًا: «الأول لابتوب، الثاني ضو المكتب»، أو «صح».")
        return
    for n, v in labels.items():
        if v.get("drop"):
            cands[n - 1]["drop"] = True
        else:
            cands[n - 1]["name"] = v["name"]
    _set_session(conn, site, t)
    _ask_save(conn, site, t)


# ---------------- for the UI ----------------

def state(conn, site: str) -> dict:
    t = session(conn, site)
    ctx = _ctx(conn, site)
    return {
        "session": t and {"room": t["room"], "room_name": nilm.room_name(conn, site, t["room"]),
                          "status": t["status"], "candidates": len(t["candidates"])},
        "waiting_for": ctx and ctx["type"],
        "meter_room": db.get_state(conn, f"meter_room:{site}"),
        "messages": messages(conn, site),
        **nilm.status(conn, site),
    }


def room_meter(conn, site: str) -> dict | None:
    """For the simulator: which room's breaker the PZEM is on (it stays there after teach mode)."""
    room = db.get_state(conn, f"meter_room:{site}")
    if not room or config.load_sites()[site]["source"] != "simulator":
        return None
    t = session(conn, site)
    return {"room": room, "started_ts": t and t["started_ts"], "guided": bool(t and t["status"] == "listening")}


def delete_fingerprint(conn, site: str, fp_id: int) -> dict:
    f = db.one(conn.execute("SELECT * FROM fingerprints WHERE site=? AND id=?", (site, fp_id)))
    if not f:
        raise actions.ActionError("البصمة مش موجودة.")
    nilm.delete_fingerprint(conn, site, fp_id)
    db.audit(conn, site, "T0", "human", "fingerprint_deleted", f"انحذفت بصمة «{f['name']}».")
    return state(conn, site)
