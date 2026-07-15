from __future__ import annotations

import json

import harness.research as research
from harness.agent import Agent
from harness.config import Config
from harness.llm import LLMResponse
from harness.research import Budget, parse_json_object, run_research


class ScriptedModel:
    """Returns queued responses; streams content through on_delta like the
    real client so stop checks run."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, temperature=0.4, max_tokens=2048,
             on_delta=None, tools=None):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        if not self.responses:
            raise AssertionError("model called more times than scripted")
        resp = self.responses.pop(0)
        if on_delta is not None and resp.content:
            on_delta("content", resp.content)
        return resp

    def reset_cancel(self) -> None:
        pass


def _agent(tmp_path, responses: list[LLMResponse],
           window: int = 32768) -> Agent:
    cfg = Config(context_window=window)
    agent = Agent(cfg, workspace=tmp_path)
    agent.llm = ScriptedModel(responses)
    return agent


def _events_collector():
    events: list[tuple[str, object]] = []
    return events, lambda etype, data: events.append((etype, data))


def test_parse_json_object_tolerates_fences_prose_and_commas() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! Here you go: {"a": [1, 2,],} thanks') == {
        "a": [1, 2]}
    assert parse_json_object("no json here") is None
    assert parse_json_object('[1, 2]') is None
    assert parse_json_object("") is None


def test_budget_scales_with_context_window() -> None:
    small = Budget.for_config(Config(context_window=8192))
    large = Budget.for_config(Config(context_window=65536))
    assert small.rounds <= 2 and small.max_sources <= 6
    assert large.rounds == 3 and large.max_sources == 12
    assert small.report_tokens < large.report_tokens

    capped = Budget.for_config(Config(
        context_window=65536, research_max_rounds=99,
        research_max_sources=999))
    assert capped.rounds == 6 and capped.max_sources == 24


def test_full_research_turn_produces_cited_report_and_saves_file(
        tmp_path, monkeypatch) -> None:
    scope = LLMResponse(content=json.dumps({
        "action": "research",
        "brief": "Compare A and B for hobbyists",
        "sub_questions": ["What is A?", "What is B?"],
        "queries": ["A overview", "B overview"],
    }))
    extract = [LLMResponse(content=json.dumps({
        "relevant": True, "title": f"S{i}",
        "notes": [f"S{i} fact one", f"S{i} fact two"],
    })) for i in (1, 2)]
    extract.append(LLMResponse(content=json.dumps({"relevant": False})))
    extract.append(LLMResponse(content=json.dumps({
        "relevant": True, "title": "S3",
        "notes": ["S3 fact one"],
    })))
    reflect = LLMResponse(content=json.dumps({"complete": True}))
    report = LLMResponse(content=(
        "# A vs B\n\n## Executive summary\nA leads for hobbyists [1]. "
        "B is cheaper [3]."))
    agent = _agent(tmp_path, [scope, *extract, reflect, report])

    def fake_search(query):
        n = 1 if query.startswith("A") else 3
        return ([{"title": f"R{n}", "url": f"https://ex.com/{n}",
                  "snippet": "s"},
                 {"title": f"R{n + 1}", "url": f"https://ex.com/{n + 1}",
                  "snippet": "s"}], "")

    monkeypatch.setattr(research, "search_results", fake_search)
    monkeypatch.setattr(
        research, "fetch_url",
        lambda url: "# Page\n" + "Long page content about the topic. " * 20)
    events, emit = _events_collector()

    final = run_research(agent, "Compare A and B", on_event=emit)

    assert "# A vs B" in final and "## Sources" in final
    assert "[1] S1 — https://ex.com/1" in final
    # source 2 was extracted but never cited, so it is not listed
    assert "S2 —" not in final
    assert "[3] S3 — https://ex.com/4" in final
    reports = list(tmp_path.glob("research-report-*.md"))
    assert len(reports) == 1
    saved = reports[0].read_text(encoding="utf-8")
    assert "## Sources" in saved and "_Report saved" not in saved
    # the exchange is persisted for follow-up turns
    assert agent.ctx.messages[-2]["role"] == "user"
    assert agent.ctx.messages[-1]["content"] == final
    tool_events = [d["name"] for t, d in events if t == "tool_call"]
    assert tool_events.count("web_search") == 2
    assert tool_events.count("fetch") == 4
    phases = [d.get("phase") for t, d in events
              if t == "activity" and isinstance(d, dict)]
    assert "research_searching" in phases and "research_writing" in phases
    assert any(t == "context" and "Deep research plan" in str(d)
               for t, d in events)


def test_ambiguous_first_turn_asks_clarifying_questions(
        tmp_path, monkeypatch) -> None:
    scope = LLMResponse(content=json.dumps({
        "action": "clarify",
        "questions": ["Which market?", "What time frame?"],
    }))
    agent = _agent(tmp_path, [scope])

    def no_search(query):
        raise AssertionError("clarify must not search")

    monkeypatch.setattr(research, "search_results", no_search)
    events, emit = _events_collector()
    final = run_research(agent, "research the market", on_event=emit)
    assert "1. Which market?" in final and "2. What time frame?" in final
    assert not list(tmp_path.glob("research-report-*.md"))


def test_unparseable_scope_falls_back_and_reports_failed_search(
        tmp_path, monkeypatch) -> None:
    agent = _agent(tmp_path, [LLMResponse(content="I think we should…")])
    monkeypatch.setattr(research, "search_results",
                        lambda query: ([], "offline"))
    events, emit = _events_collector()
    final = run_research(agent, "history of the metric system", on_event=emit)
    assert "could not gather usable sources" in final
    assert "history of the metric system" in final
    assert agent.ctx.messages[-1]["content"] == final


def test_stop_before_first_model_call_returns_stopped(tmp_path) -> None:
    agent = _agent(tmp_path, [])
    agent._stop.set()
    final = run_research(agent, "anything", on_event=None)
    assert final == "(stopped by user)"
    assert not agent._stop.is_set()
    assert agent.ctx.messages[-1]["content"] == "(stopped by user)"


def test_steer_folds_into_brief_at_round_boundary(
        tmp_path, monkeypatch) -> None:
    scope = LLMResponse(content=json.dumps({
        "action": "research", "brief": "Original brief",
        "sub_questions": [], "queries": ["q1"],
    }))
    extract = LLMResponse(content=json.dumps({
        "relevant": True, "title": "S1", "notes": ["fact"]}))
    reflect = LLMResponse(content=json.dumps({"complete": True}))
    report = LLMResponse(content="# R\n\nDone [1].")
    agent = _agent(tmp_path, [scope, extract, reflect, report])
    monkeypatch.setattr(research, "search_results", lambda query: (
        [{"title": "R", "url": "https://ex.com/a", "snippet": "s"}], ""))
    monkeypatch.setattr(research, "fetch_url",
                        lambda url: "content " * 40)

    steered: list[str] = []

    def emit(etype, data):
        if etype == "activity" and data.get("phase") == "research_scoping":
            # a steer arriving while the pipeline is already running
            assert agent.submit_steer("focus on Europe only")
        if etype == "steer_applied":
            steered.append(str(data))

    run_research(agent, "topic", on_event=emit)
    assert steered == ["focus on Europe only"]
    model = agent.llm
    synth_prompt = model.calls[-1]["messages"][1]["content"]
    assert "focus on Europe only" in synth_prompt
