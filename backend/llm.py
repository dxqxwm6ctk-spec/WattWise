"""LLM planner and explainer (optional layer on top of the rule-based agent).

What the LLM is allowed to do:
  - split the goal into a short Arabic plan,
  - look at the data through tools (sensors, weather, tariff, detected waste),
  - choose ONE of the waste candidates (or none) and explain it in plain Arabic.

What it is NOT allowed to do: switch anything. Its choice goes back to the
agent loop, which asks the Policy Guard again and then asks the human.
If there is no key, no internet, the budget is spent, or the answer is late or
broken, the agent uses the rule-based planner instead (fallback).

The provider is behind a tiny interface (`Provider.run`), so another model
provider can be added without touching the agent.
"""

import json
import time
from dataclasses import dataclass, field

from backend import config, db, weather


class ProviderError(Exception):
    """The provider could not give a usable answer (network, API error, refusal...)."""


@dataclass
class RunResult:
    final_tool: str | None = None       # name of the "final" tool the model called
    final_input: dict = field(default_factory=dict)
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class Provider:
    """Interface: run a tool-use conversation until the model calls a final tool."""

    name = "base"
    model = ""

    def run(self, system: str, user: str, tools: list[dict], call_tool, final_tools: set[str]) -> RunResult:
        raise NotImplementedError


class AnthropicProvider(Provider):
    """Claude through the official `anthropic` SDK, manual tool loop."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        import anthropic  # imported here so the app runs even without the package

        self._anthropic = anthropic
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, timeout=config.LLM_TIMEOUT_S, max_retries=1)

    def run(self, system, user, tools, call_tool, final_tools):
        api_tools = [{**t, "strict": True} for t in tools]
        messages = [{"role": "user", "content": user}]
        result = RunResult()
        for _ in range(config.LLM_MAX_TOOL_ROUNDS):
            try:
                r = self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=8000,
                    system=system,
                    tools=api_tools,
                    messages=messages,
                    output_config={"effort": "low"},  # small decision, keep it cheap
                    # If the model declines, the API retries on a fallback model by itself.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
            except self._anthropic.APIError as e:
                raise ProviderError(f"{type(e).__name__}") from e
            result.input_tokens += r.usage.input_tokens or 0
            result.output_tokens += r.usage.output_tokens or 0

            if r.stop_reason == "refusal":
                raise ProviderError("refusal")
            messages.append({"role": "assistant", "content": r.content})
            if r.stop_reason == "pause_turn":
                continue
            calls = [b for b in r.content if b.type == "tool_use"]
            if not calls:
                result.text = "".join(b.text for b in r.content if b.type == "text")
                return result
            tool_results = []
            for b in calls:
                if b.name in final_tools:
                    result.final_tool, result.final_input = b.name, dict(b.input)
                    return result
                out = call_tool(b.name, dict(b.input))
                tool_results.append({"type": "tool_result", "tool_use_id": b.id,
                                     "content": json.dumps(out, ensure_ascii=False, default=str)})
            messages.append({"role": "user", "content": tool_results})
        raise ProviderError("too_many_rounds")


# ---------------- availability and spending cap ----------------

_provider: Provider | None = None
_down_until = 0.0          # after a failure, do not wait for the LLM again for a while
DOWN_BACKOFF_S = 300


def set_provider(p: Provider | None) -> None:
    """Used by tests (fake provider) and by get_provider()."""
    global _provider, _down_until
    _provider, _down_until = p, 0.0


def get_provider() -> Provider | None:
    global _provider
    if _provider is None and config.LLM_PROVIDER == "anthropic" and config.LLM_API_KEY:
        try:
            _provider = AnthropicProvider(config.LLM_API_KEY, config.LLM_MODEL)
        except ImportError:
            return None
    return _provider


def _month_key() -> str:
    return "llm_spend:" + time.strftime("%Y-%m")


def spent_usd(conn) -> float:
    return float(db.get_state(conn, _month_key(), 0.0))


def add_spend(conn, result: RunResult) -> float:
    cost = (result.input_tokens * config.LLM_PRICE_IN_PER_MTOK
            + result.output_tokens * config.LLM_PRICE_OUT_PER_MTOK) / 1_000_000
    db.set_state(conn, _month_key(), round(spent_usd(conn) + cost, 6))
    return cost


def mark_down() -> None:
    global _down_until
    _down_until = time.time() + DOWN_BACKOFF_S


def status(conn) -> dict:
    """Which brain is in charge right now, and why (shown in the UI)."""
    spent, budget = spent_usd(conn), config.LLM_MONTHLY_BUDGET_USD
    base = {"spent_usd": round(spent, 4), "budget_usd": budget}
    p = get_provider()
    if p is None:
        return {**base, "mode": "rules", "reason_ar": "بدون نموذج ذكاء اصطناعي (ما في مفتاح). شغّالين بالقواعد."}
    if spent >= budget:
        return {**base, "mode": "rules", "model": p.model, "reason_ar": "خلصت ميزانية الشهر. رجعنا للقواعد."}
    if time.time() < _down_until:
        return {**base, "mode": "rules", "model": p.model, "reason_ar": "النموذج ما ردّ (نت أو خطأ). شغّالين بالقواعد مؤقتًا."}
    return {**base, "mode": "llm", "model": p.model, "reason_ar": "النموذج بيخطط وبيشرح، والقواعد والموافقة بالكود."}


def available(conn) -> bool:
    return status(conn)["mode"] == "llm"


# ---------------- tools the model can call ----------------
# Handlers only read a snapshot taken by the agent loop (plus the weather),
# so nothing here can change a device.

SNAPSHOT_TOOLS = [
    {"name": "read_sensors",
     "description": "Latest meter power and every room's temperature, light, occupancy and window state, plus devices that are on.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"name": "get_weather",
     "description": "Outdoor temperature and solar radiation now (Open-Meteo). available=false when offline.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"name": "forecast_load",
     "description": "Expected average watts for this hour and the next 5, with kWh, JOD and measured forecast accuracy.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"name": "get_tariff",
     "description": "Tariff type, this month's kWh, and the price of the next kWh in JOD.",
     "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
]


def _snapshot_handler(snapshot: dict):
    def call(name: str, _input: dict) -> dict:
        if name == "get_weather":
            return weather.get_weather()
        if name in snapshot:
            return snapshot[name]
        return {"error": f"unknown tool {name}"}
    return call


# ---------------- job 1: split the goal into a plan ----------------

PLAN_SYSTEM = (
    "You are WattWise, an energy-saving agent for a small home or lab in Jordan. "
    "The owner gives you a goal. Split it into 3 to 6 short, concrete steps you will follow, "
    "in simple Jordanian Arabic, one sentence each. You can read sensors, weather and the tariff first. "
    "Rules you cannot change: you never switch a device without the owner's approval, "
    "you never touch critical loads (fridge, fire alarm, medical, emergency light), and comfort limits "
    "are enforced in code. Do not promise savings numbers; savings are only counted after the meter confirms them. "
    "Finish by calling submit_plan."
)

PLAN_FINAL = {
    "name": "submit_plan",
    "description": "Submit the plan: 3 to 6 Arabic steps and a one-sentence Arabic summary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps_ar": {"type": "array", "items": {"type": "string"}},
            "summary_ar": {"type": "string"},
        },
        "required": ["steps_ar", "summary_ar"],
        "additionalProperties": False,
    },
}


def plan_goal(provider: Provider, goal_text: str, bill_target_jd, snapshot: dict) -> tuple[dict | None, RunResult]:
    user = json.dumps({"goal": goal_text, "bill_target_jd": bill_target_jd}, ensure_ascii=False)
    r = provider.run(PLAN_SYSTEM, user, SNAPSHOT_TOOLS + [PLAN_FINAL], _snapshot_handler(snapshot), {"submit_plan"})
    if r.final_tool != "submit_plan":
        return None, r
    steps = [str(s).strip() for s in r.final_input.get("steps_ar", []) if str(s).strip()][:6]
    if len(steps) < 2:
        return None, r
    return {"steps": steps, "summary": str(r.final_input.get("summary_ar", "")).strip()}, r


# ---------------- job 2: choose and explain one action ----------------

DECIDE_SYSTEM = (
    "You are WattWise, an energy-saving agent. The detect_waste tool lists devices running in empty rooms; "
    "each one already passed the safety checks. Look at the data you need, then either call propose_action "
    "for the ONE candidate that is most worth switching off now, or call no_action if switching is not a good idea "
    "(for example a short absence, or it would hurt comfort). Write in simple Jordanian Arabic, short, "
    "with the real numbers from the tools (watts, JOD per hour). Never invent numbers. "
    "The owner must approve; you only suggest."
)


def decide_tools(candidate_ids: list[str]) -> list[dict]:
    return SNAPSHOT_TOOLS + [
        {"name": "detect_waste",
         "description": "Devices that are on in rooms that have been empty for a while, with watts and saving per hour.",
         "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
        {"name": "propose_action",
         "description": "Ask the owner to approve switching OFF one candidate device.",
         "input_schema": {
             "type": "object",
             "properties": {
                 "device_id": {"type": "string", "enum": candidate_ids},
                 "title_ar": {"type": "string", "description": "Short question, e.g. نطفي مكيّف غرفة النوم؟"},
                 "reason_ar": {"type": "string", "description": "Why, with numbers, 1-2 sentences."},
                 "alternative_ar": {"type": "string", "description": "What happens if the owner says no."},
             },
             "required": ["device_id", "title_ar", "reason_ar", "alternative_ar"],
             "additionalProperties": False,
         }},
        {"name": "no_action",
         "description": "Decide not to propose anything now.",
         "input_schema": {"type": "object", "properties": {"reason_ar": {"type": "string"}},
                          "required": ["reason_ar"], "additionalProperties": False}},
    ]


def decide(provider: Provider, goal_text: str, snapshot: dict) -> tuple[dict | None, RunResult]:
    ids = [c["device_id"] for c in snapshot["detect_waste"]]
    user = json.dumps({"goal": goal_text}, ensure_ascii=False)
    r = provider.run(DECIDE_SYSTEM, user, decide_tools(ids), _snapshot_handler(snapshot), {"propose_action", "no_action"})
    if r.final_tool == "no_action":
        return {"action": "none", "reason": str(r.final_input.get("reason_ar", "")).strip()}, r
    if r.final_tool == "propose_action" and r.final_input.get("device_id") in ids:
        i = r.final_input
        return {"action": "propose", "device_id": i["device_id"],
                "title": str(i.get("title_ar", "")).strip()[:120],
                "reason": str(i.get("reason_ar", "")).strip()[:600],
                "alternative": str(i.get("alternative_ar", "")).strip()[:300]}, r
    return None, r


# ---------------- job 3: read the owner's reply in "teach mode" ----------------

READ_SYSTEM = (
    "You help WattWise, an energy agent, understand the owner's short reply in Jordanian Arabic. "
    "The meter found some electrical devices (numbered candidates with watts and a guess). "
    "The owner may confirm the guesses (intent yes), refuse (no), give names to some numbers (labels), "
    "or ask to ignore some (ignore, with ignore=true on those items). For one unknown device, the reply "
    "is usually its name and maybe its room; put the name in item n=1 and the room id in room_id. "
    "Use only the numbers and room ids given. Keep names short, in the owner's words. Never invent devices. "
    "Call submit_reading once."
)


def read_tools(room_ids: list[str]) -> list[dict]:
    return [{
        "name": "submit_reading",
        "description": "What the owner's reply means.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["yes", "no", "labels", "ignore", "unclear"]},
                "items": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"n": {"type": "integer"}, "name": {"type": "string"},
                                   "ignore": {"type": "boolean"}},
                    "required": ["n", "name", "ignore"], "additionalProperties": False}},
                "room_id": {"type": "string", "enum": room_ids + [""]},
            },
            "required": ["intent", "items", "room_id"],
            "additionalProperties": False,
        },
    }]


def read_reply(provider: Provider, question: str, candidates: list[dict], rooms: list[dict],
               reply: str) -> tuple[dict | None, RunResult]:
    """Returns {"intent", "items", "room_id"} or None when the answer is unusable (rules take over)."""
    user = json.dumps({"question_type": question, "candidates": candidates, "rooms": rooms, "reply": reply},
                      ensure_ascii=False)
    r = provider.run(READ_SYSTEM, user, read_tools([x["id"] for x in rooms]), lambda *_: {}, {"submit_reading"})
    if r.final_tool != "submit_reading" or r.final_input.get("intent") == "unclear":
        return None, r
    i = r.final_input
    items = [it for it in i.get("items", []) if isinstance(it, dict)]
    return {"intent": i.get("intent"), "items": items, "room_id": i.get("room_id") or ""}, r
