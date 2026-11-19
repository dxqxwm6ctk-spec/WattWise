"""LLM layer with a fake provider: plan, choice, Policy Guard, budget cap, fallback."""

from concurrent.futures import Future

import pytest

from backend import actions, agent, config, db, llm
from tests.test_flow import reading


class FakeProvider(llm.Provider):
    """Plays a scripted model: calls some tools, then a final tool."""

    name, model = "fake", "fake-model"

    def __init__(self, final=None, error=None, tokens=(1000, 200), reads=("read_sensors", "detect_waste")):
        self.final, self.error, self.tokens, self.reads = final, error, tokens, reads
        self.seen = {}

    def run(self, system, user, tools, call_tool, final_tools):
        if self.error:
            raise self.error
        names = {t["name"] for t in tools}
        for n in self.reads:
            if n in names:
                self.seen[n] = call_tool(n, {})
        name, data = self.final(names) if callable(self.final) else self.final
        assert name in final_tools
        return llm.RunResult(final_tool=name, final_input=data,
                             input_tokens=self.tokens[0], output_tokens=self.tokens[1])


def plan_or(choice):
    """Answer submit_plan for plan jobs and `choice` for decision jobs."""
    def pick(names):
        if "submit_plan" in names:
            return "submit_plan", {"steps_ar": ["خطوة ١", "خطوة ٢", "خطوة ٣"], "summary_ar": "ملخص"}
        return choice
    return pick


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "WASTE_EMPTY_S", 0)
    monkeypatch.setattr(config, "ANALYZE_S", 0)
    monkeypatch.setattr(config, "VERIFY_AFTER_S", 0)
    monkeypatch.setattr(config, "LLM_MONTHLY_BUDGET_USD", 5)

    def run_now(fn, *args):     # run LLM jobs synchronously in tests
        f = Future()
        try:
            f.set_result(fn(*args))
        except Exception as e:
            f.set_exception(e)
        return f

    monkeypatch.setattr(agent, "_submit", run_now)
    agent._analyzing.clear()
    agent._jobs.clear()
    agent._plan_jobs.clear()
    db.init_db()
    with db.connect() as c:
        yield c


def run_until_pending(conn, ticks=5):
    for _ in range(ticks):
        agent.tick(conn, "home")
        if actions.pending_approval(conn, "home"):
            break
    return actions.pending_approval(conn, "home")


def start(conn, provider):
    llm.set_provider(provider)
    actions.set_goal(conn, "home", "خلّي الفاتورة تحت ٣٠ دينار", 30)
    actions.ingest(conn, reading(2500, bedroom_occupied=False, window=True))


def test_no_key_means_rules(conn):
    assert llm.status(conn)["mode"] == "rules"
    actions.set_goal(conn, "home", "goal", None)
    assert db.get_state(conn, "plan:home")["by"] == "rules"


def test_llm_plans_the_goal(conn):
    start(conn, FakeProvider(final=plan_or(("no_action", {"reason_ar": "x"}))))
    agent.tick(conn, "home")
    agent.tick(conn, "home")
    plan = db.get_state(conn, "plan:home")
    assert plan["by"] == "llm" and plan["steps"] == ["خطوة ١", "خطوة ٢", "خطوة ٣"]


def test_llm_explains_the_proposal(conn):
    choice = ("propose_action", {"device_id": "bedAc", "title_ar": "نطفي المكيّف؟",
                                 "reason_ar": "الغرفة فاضية والشباك مفتوح.", "alternative_ar": "بنخلّيه."})
    p = FakeProvider(final=plan_or(choice))
    start(conn, p)
    a = run_until_pending(conn)
    assert a["device_id"] == "bedAc" and a["reason"] == "الغرفة فاضية والشباك مفتوح."
    # The LLM only saw candidates that already passed the Policy Guard; nothing critical.
    ids = [w["device_id"] for w in p.seen["detect_waste"]]
    assert "fridge" not in ids and "router" not in ids
    # Still nothing switched: the human must approve.
    assert db.device(conn, "home", "bedAc")["is_on"] == 1


def test_llm_cannot_pick_a_device_outside_the_candidates(conn):
    choice = ("propose_action", {"device_id": "fridge", "title_ar": "x", "reason_ar": "x", "alternative_ar": "x"})
    start(conn, FakeProvider(final=plan_or(choice)))
    a = run_until_pending(conn)
    # Invalid answer -> rule-based fallback proposes the real waste, never the fridge.
    assert a["device_id"] == "bedAc"
    events = [r["event"] for r in db.rows(conn.execute("SELECT event FROM audit_log"))]
    assert "llm_fallback" in events


def test_llm_no_action_means_no_question(conn):
    start(conn, FakeProvider(final=plan_or(("no_action", {"reason_ar": "غياب قصير"}))))
    for _ in range(5):
        agent.tick(conn, "home")
    assert actions.pending_approval(conn, "home") is None


def test_provider_error_falls_back_to_rules(conn):
    start(conn, FakeProvider(error=llm.ProviderError("APIConnectionError")))
    a = run_until_pending(conn)
    assert a is not None and a["device_id"] == "bedAc"
    assert llm.status(conn)["mode"] == "rules"     # backs off after a failure


def test_budget_cap_switches_to_rules(conn, monkeypatch):
    monkeypatch.setattr(config, "LLM_MONTHLY_BUDGET_USD", 0.01)
    # 1000 in + 200 out tokens at 4/20 USD per MTok = 0.008 USD per call.
    start(conn, FakeProvider(final=plan_or(("no_action", {"reason_ar": "x"}))))
    assert llm.status(conn)["mode"] == "llm"
    llm.add_spend(conn, llm.RunResult(input_tokens=1000, output_tokens=200))
    llm.add_spend(conn, llm.RunResult(input_tokens=1000, output_tokens=200))
    assert llm.spent_usd(conn) >= 0.01
    assert llm.status(conn)["mode"] == "rules"
    a = run_until_pending(conn)
    # Over budget: the LLM is not called; the rules still find and explain the waste.
    assert a is not None and a["device_id"] == "bedAc"
    assert '"explained_by": "rules"' in a["details"]
    assert db.get_state(conn, "plan:home")["by"] == "rules"


def test_anthropic_provider_tool_loop(monkeypatch):
    """The real provider's loop, with the API call replaced (no network, no key)."""
    from types import SimpleNamespace as NS

    p = llm.AnthropicProvider(api_key="test", model="claude-opus-5-5")
    replies = [
        NS(stop_reason="tool_use", usage=NS(input_tokens=100, output_tokens=10),
           content=[NS(type="tool_use", id="t1", name="get_tariff", input={})]),
        NS(stop_reason="tool_use", usage=NS(input_tokens=200, output_tokens=20),
           content=[NS(type="text", text="ok"),
                    NS(type="tool_use", id="t2", name="no_action", input={"reason_ar": "لا"})]),
    ]
    sent = []

    def create(**kw):
        sent.append(kw)
        return replies[len(sent) - 1]

    monkeypatch.setattr(p.client.beta.messages, "create", create)
    calls = []
    r = p.run("sys", "goal", llm.decide_tools(["bedAc"]), lambda n, i: calls.append(n) or {"price": 0.1},
              {"propose_action", "no_action"})
    assert calls == ["get_tariff"]
    assert r.final_tool == "no_action" and r.input_tokens == 300 and r.output_tokens == 30
    assert sent[0]["fallbacks"] == "default" and all(t["strict"] for t in sent[0]["tools"])
    # Second request carries the assistant turn and the tool result.
    assert sent[1]["messages"][2]["content"][0]["tool_use_id"] == "t1"


def test_anthropic_provider_refusal_is_an_error(monkeypatch):
    from types import SimpleNamespace as NS

    p = llm.AnthropicProvider(api_key="test", model="claude-opus-5-5")
    monkeypatch.setattr(p.client.beta.messages, "create",
                        lambda **kw: NS(stop_reason="refusal", usage=NS(input_tokens=1, output_tokens=0), content=[]))
    with pytest.raises(llm.ProviderError):
        p.run("s", "u", llm.SNAPSHOT_TOOLS, lambda n, i: {}, {"x"})
