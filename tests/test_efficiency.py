from __future__ import annotations

import copy
import json
import threading
import time

from harness import mcp_client, skills
from harness.agent import Agent, _repair_json_object
from harness.config import Config
from harness.context import ContextManager, _fallback_summary
from harness.llm import LLMResponse
from harness.skills import SkillsManager
from harness.tokens import estimate_text, estimate_tools
from harness.tool_policy import select_tool_policy
from harness.tools import build_registry
from harness.tools import web
import harness.tools as tools_module


def test_compact_code_turn_uses_a_bounded_relevant_prompt(tmp_path) -> None:
    agent = Agent(Config(context_window=4096), workspace=tmp_path)
    try:
        text = "audit and fix this entire repository end to end"
        policy = select_tool_policy(text, 4096)
        agent._turn_policy = policy
        agent._turn_tool_names = policy.names
        for name in agent.skills.recommend(text, limit=policy.skill_limit):
            agent.skills.activate(name)
        names = {s["function"]["name"] for s in agent._tool_schemas()}
        assert {"read_file", "search", "edit_file", "run", "skill"} <= names
        assert not {"browser", "computer", "remember", "subtask"} & names
        fixed = (estimate_text(agent.system_prompt())
                 + estimate_tools(agent._tool_schemas()))
        assert fixed < 4096 * 0.55
    finally:
        agent.llm.close()


def test_tool_policy_routes_signed_in_browser_and_office_work() -> None:
    browser = select_tool_policy("open Gmail in my signed-in Chrome", 8192)
    assert {"browser", "computer"} <= browser.names
    office = select_tool_policy("create an xlsx financial model", 4096)
    assert {"write_file", "read_file", "run"} <= office.names
    creative = select_tool_policy("animate a plane in Blender", 8192)
    assert {"write_file", "read_file", "run"} <= creative.names
    casual = select_tool_policy("hello there", 4096)
    assert casual.names == frozenset({"skill"})


def test_safe_tool_json_repair_handles_small_model_formatting_only() -> None:
    assert _repair_json_object('```json\n{"path":"a.txt",}\n```') == \
        '{"path":"a.txt"}'
    assert _repair_json_object('{"command":"remove everything"') is None
    assert _repair_json_object('[1, 2]') is None


def test_agent_hides_direct_mcp_schemas_but_registry_can_diagnose_them(
        tmp_path, monkeypatch) -> None:
    direct = {"type": "function", "function": {
        "name": "remote_expensive_tool", "description": "x",
        "parameters": {"type": "object", "properties": {}},
    }}

    class Hub:
        def schemas(self, include_builtin=True):
            return [direct]

    monkeypatch.setattr(mcp_client, "MCP_HUB", Hub())
    agent = Agent(Config(), workspace=tmp_path)
    try:
        all_names = {s["function"]["name"] for s in agent.tools.schemas()}
        prompt_names = {s["function"]["name"] for s in agent._tool_schemas()}
        assert "remote_expensive_tool" in all_names
        assert "remote_expensive_tool" not in prompt_names
    finally:
        agent.llm.close()


def test_skill_search_activation_and_standard_saved_frontmatter(
        tmp_path, monkeypatch) -> None:
    root = tmp_path / "catalog"
    md = root / "browser-helper" / "SKILL.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\nname: browser-helper\n"
        "description: Operate websites through semantic browser references.\n"
        "---\nFIRST RULE\n" + "details " * 1000 + "\nLAST RULE\n",
        encoding="utf-8",
    )
    manager = SkillsManager((root,))
    assert "browser-helper" in manager.search("operate browser website")
    loaded = manager.load("browser-helper")
    # v2.3.x regression fix: instructions must arrive inline in the tool
    # result — small models act on what the call returns, not on a block
    # that only appears in the next request's system prompt.
    assert "activated" in loaded and "FIRST RULE" in loaded
    assert "already active" in manager.load("browser-helper")
    active = manager.active_text(600)
    assert "FIRST RULE" in active and "LAST RULE" in active
    assert "condensed for context budget" in active
    assert len(active) < 750

    user_dir = tmp_path / "user-skills"
    monkeypatch.setattr(skills, "USER_SKILLS_DIR", user_dir)
    monkeypatch.setattr(skills, "BUILTIN_SKILLS_DIR", tmp_path / "builtins")
    assert skills.save_skill("learned", "short useful hint", "Do the thing.").startswith("Saved")
    raw = (user_dir / "learned" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = raw.split("---", 2)[1]
    assert "name:" in frontmatter and "description:" in frontmatter
    assert "category:" not in frontmatter and "hint:" not in frontmatter


def test_zero_tool_retention_fades_prior_turn_results() -> None:
    ctx = ContextManager(Config(tool_result_keep_turns=0))
    ctx.messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "x", "type": "function",
            "function": {"name": "run", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "x", "name": "run",
         "content": "large " + "x" * 1000},
        {"role": "user", "content": "second"},
    ]
    ctx._fade_old_tool_results()
    assert ctx.messages[2]["content"].startswith("[old tool result")


def test_fallback_handoff_keeps_later_user_constraints() -> None:
    summary = _fallback_summary([
        {"role": "user", "content": "Build the dashboard"},
        {"role": "assistant", "content": "working"},
        {"role": "user", "content": "Keep authentication unchanged"},
        {"role": "user", "content": "Use teal and support mobile"},
    ], RuntimeError("offline"))
    assert "Build the dashboard" in summary
    assert "Keep authentication unchanged" in summary
    assert "Use teal and support mobile" in summary


def test_output_limit_continues_twice_and_reports_model_wait(tmp_path) -> None:
    agent = Agent(Config(max_iterations=5), workspace=tmp_path)
    agent.tool_mode = False
    agent.llm.close()
    calls: list[list[dict]] = []

    class Model:
        def chat(self, messages, **kwargs):
            calls.append(copy.deepcopy(messages))
            part = len(calls)
            return LLMResponse(
                content={1: "alpha", 2: "beta", 3: "gamma"}[part],
                finish_reason="length" if part < 3 else "stop",
            )

        def cancel_current(self):
            pass

    agent.llm = Model()  # type: ignore[assignment]
    events: list[tuple[str, object]] = []
    result = agent.run_turn(
        "write a long answer", stream=False,
        on_event=lambda kind, data: events.append((kind, data)))
    assert result == "alpha\nbeta\ngamma"
    assert any("Harness continuation" in str(m.get("content", ""))
               for m in calls[1])
    assert any(kind == "activity" and isinstance(data, dict)
               and data.get("phase") == "model_wait"
               for kind, data in events)


def test_reasoning_only_length_response_gets_an_answer_pass(tmp_path) -> None:
    agent = Agent(Config(max_iterations=3), workspace=tmp_path)
    agent.tool_mode = False
    agent.llm.close()
    calls = 0

    class Model:
        def chat(self, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return LLMResponse(
                    reasoning="I have the answer but used the whole budget.",
                    finish_reason="length")
            return LLMResponse(content="final answer", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.llm = Model()  # type: ignore[assignment]
    assert agent.run_turn("answer carefully", stream=False) == "final answer"
    assert calls == 2


def test_repeated_identical_tool_failure_stops_early(tmp_path) -> None:
    agent = Agent(Config(max_iterations=20), workspace=tmp_path)
    agent.llm.close()
    calls = 0

    class Tools:
        def schemas(self):
            return []

        def execute(self, name, arguments, agent=None):
            return "Error: same failure"

    class Model:
        def chat(self, **kwargs):
            nonlocal calls
            calls += 1
            return LLMResponse(tool_calls=[{
                "id": f"c{calls}", "type": "function",
                "function": {"name": "noop", "arguments": "{}"},
            }], finish_reason="tool_calls")

        def cancel_current(self):
            pass

    agent.tools = Tools()  # type: ignore[assignment]
    agent.llm = Model()  # type: ignore[assignment]
    result = agent.run_turn("do it", stream=False)
    assert "repeated identical tool attempts" in result
    assert calls == 4


def test_computer_forwards_stop_event_to_native_hub(
        tmp_path, monkeypatch) -> None:
    executable = tmp_path / "computer"
    executable.write_bytes(b"placeholder")
    monkeypatch.setenv("LMH_COMPUTER_USE_BIN", str(executable))
    received = []

    class Hub:
        def schemas(self, include_builtin=True):
            return []

        def has_tool(self, name):
            return name == "computer_list_apps"

        def call(self, name, arguments, stop_event=None):
            received.append(stop_event)
            return "apps"

    class SkillStub:
        def load(self, name):
            return name

        def search(self, query):
            return query

    monkeypatch.setattr(mcp_client, "MCP_HUB", Hub())
    registry = build_registry(SkillStub())

    class AgentStub:
        _stop = threading.Event()

    assert registry.execute(
        "computer", json.dumps({"action": "list_apps"}),
        agent=AgentStub()) == "apps"
    assert received == [AgentStub._stop]


def test_web_tool_returns_promptly_when_turn_is_stopped(monkeypatch) -> None:
    def slow_search(query):
        time.sleep(2)
        return query

    monkeypatch.setattr(tools_module, "web_search", slow_search)

    class SkillStub:
        def load(self, name):
            return name

        def search(self, query):
            return query

    registry = build_registry(SkillStub())

    class AgentStub:
        _stop = threading.Event()

    AgentStub._stop.set()
    started = time.monotonic()
    result = registry.execute(
        "web_search", json.dumps({"query": "anything"}), agent=AgentStub())
    assert result == "Error: network tool stopped by user."
    assert time.monotonic() - started < 0.5


def test_remote_reader_is_opt_in_and_rejects_query_urls(monkeypatch) -> None:
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(args[0])
        raise AssertionError("network should not be reached")

    monkeypatch.setattr(web.httpx, "get", fake_get)
    monkeypatch.delenv("LMH_ALLOW_REMOTE_READER", raising=False)
    assert web._jina_reader("https://example.com/public") is None
    monkeypatch.setenv("LMH_ALLOW_REMOTE_READER", "1")
    assert web._jina_reader("https://example.com/?token=secret") is None
    assert calls == []
