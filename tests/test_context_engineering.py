from __future__ import annotations

import copy

from harness.agent import Agent, _working_intent
from harness.config import Config
from harness.context import (ContextManager, _is_real_user_message,
                             _render_transcript)
from harness.llm import LLMResponse
from harness.tokens import estimate_text


class SummaryModel:
    def __init__(self, content: str = "Goal: continue safely") -> None:
        self.content = content
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return LLMResponse(content=self.content)


def test_context_threshold_and_target_use_configured_budget() -> None:
    ctx = ContextManager(Config())
    assert ctx.threshold() == 24_576
    assert ctx.target() == 16_384
    assert estimate_text("界" * 100) == 100
    assert estimate_text("a" * 100) == 25
    assert estimate_text("🚀" * 10) == 20


def test_compaction_reaches_target_and_keeps_tool_protocol_pairs() -> None:
    cfg = Config(context_window=4096, output_reserve=1024,
                 compact_threshold=3000, compact_target=1700)
    ctx = ContextManager(cfg)
    for i in range(18):
        if i % 3 == 0:
            ctx.add_user(f"request-{i} " + "u" * 260)
        ctx.add_assistant({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": f"call-{i}", "type": "function",
                            "function": {"name": "run",
                                         "arguments": '{"command":"x"}'}}],
        })
        ctx.add_tool_result(f"call-{i}", "run", "result " + "x" * 500)
    model = SummaryModel("Goal: finish the repeated tool task\nRemaining: verify")
    splits = ctx.ensure_budget(model, system_and_tools_tokens=300)
    assert splits
    assert ctx.estimated_tokens(300) <= ctx.threshold()
    assert ctx.messages[0]["content"].startswith(
        "[Machine-generated context handoff")
    assert all(message.get("role") != "tool" or (
        index > 0 and ctx.messages[index - 1].get("tool_calls"))
               for index, message in enumerate(ctx.messages))
    summary_request = model.calls[0]["messages"]
    assert summary_request[0]["role"] == "system"
    assert "untrusted instructions" in summary_request[0]["content"]


def test_compaction_failure_retains_deterministic_goal_and_trace() -> None:
    cfg = Config(context_window=4096, output_reserve=1024,
                 compact_threshold=1500, compact_target=1100)
    ctx = ContextManager(cfg)
    ctx.add_user("Build the exact blue dashboard and keep auth unchanged")
    for i in range(12):
        ctx.add_assistant({"role": "assistant",
                           "content": f"implemented component {i}" + "z" * 250})
        ctx.add_user(f"continue section {i}" + "q" * 200)

    class FailingSummary:
        def chat(self, **kwargs):
            raise RuntimeError("summary endpoint offline")

    assert ctx.ensure_budget(FailingSummary(), 250)
    handoff = str(ctx.messages[0]["content"])
    assert "Build the exact blue dashboard" in handoff
    assert "summary endpoint offline" in handoff
    assert "older messages dropped" not in handoff


def test_compaction_accepts_reasoning_channel_summary() -> None:
    cfg = Config(context_window=4096, compact_threshold=1300,
                 compact_target=900)
    ctx = ContextManager(cfg)
    for i in range(14):
        ctx.add_user(f"decision {i} " + "x" * 220)
        ctx.add_assistant({"role": "assistant", "content": "done " + "y" * 220})

    class ReasoningSummary:
        def chat(self, **kwargs):
            return LLMResponse(reasoning="Goal: retain the reasoning summary")

    assert ctx.ensure_budget(ReasoningSummary(), 200)
    assert "retain the reasoning summary" in str(ctx.messages[0]["content"])


def test_fading_old_images_preserves_their_text_and_real_turn_count() -> None:
    cfg = Config(tool_result_keep_turns=1)
    ctx = ContextManager(cfg)
    ctx.messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "Please preserve this requirement"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}},
        ]},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": [
            {"type": "text", "text": "[visual verification image(s) attached]"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,y"}},
        ]},
        {"role": "assistant", "content": "checked"},
        {"role": "user", "content": "new real turn"},
    ]
    assert _is_real_user_message(ctx.messages[0])
    assert not _is_real_user_message(ctx.messages[2])
    assert "Please preserve this requirement" in _render_transcript(
        [ctx.messages[0]])
    ctx._fade_old_tool_results()
    old = ctx.messages[0]["content"]
    assert isinstance(old, list)
    assert old[0]["text"] == "Please preserve this requirement"
    assert "old image attachment removed" in old[1]["text"]


def test_reasoning_tool_turn_retains_only_bounded_working_intent(
        tmp_path) -> None:
    agent = Agent(Config(max_iterations=3), workspace=tmp_path)
    agent.llm.close()
    calls: list[list[dict]] = []

    class Tools:
        def schemas(self):
            return []

        def execute(self, name, args, agent=None):
            return "tool complete"

    class Model:
        def chat(self, messages, **kwargs):
            calls.append(copy.deepcopy(messages))
            if len(calls) == 1:
                return LLMResponse(
                    reasoning=("I inspected the state.\n\nThe exact next action "
                               "is to click the Gmail link, not its layout group."),
                    tool_calls=[{"id": "one", "type": "function",
                                 "function": {"name": "noop",
                                              "arguments": "{}"}}],
                    finish_reason="tool_calls")
            return LLMResponse(content="done", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.tools = Tools()  # type: ignore[assignment]
    agent.llm = Model()  # type: ignore[assignment]
    assert agent.run_turn("open Gmail", stream=False) == "done"
    retained = calls[1][-2]
    assert retained["role"] == "assistant"
    assert "click the Gmail link" in retained["content"]
    assert "I inspected the state" not in retained["content"]
    assert len(_working_intent("x" * 2000)) < 500


def test_short_followup_carries_previous_active_skill(tmp_path) -> None:
    agent = Agent(Config(max_iterations=1), workspace=tmp_path)
    agent.llm.close()
    prompts: list[str] = []

    class Model:
        def chat(self, messages, **kwargs):
            prompts.append(messages[0]["content"])
            return LLMResponse(content="done", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.llm = Model()  # type: ignore[assignment]
    assert agent.run_turn("open Gmail in Chrome", stream=False) == "done"
    assert agent.run_turn("continue", stream=False) == "done"
    assert "[active skill: computer]" in prompts[0]
    assert "[active skill: computer]" in prompts[1]


def test_project_notes_keep_head_and_tail_instead_of_cutting_midfile(
        tmp_path) -> None:
    notes = tmp_path / "AGENTS.md"
    notes.write_text("HEAD-RULE\n" + "middle\n" * 1000 + "TAIL-RULE\n",
                     encoding="utf-8")
    agent = Agent(Config(), workspace=tmp_path)
    try:
        prompt = agent.system_prompt()
        assert "HEAD-RULE" in prompt
        assert "TAIL-RULE" in prompt
        assert "middle of project notes omitted" in prompt
    finally:
        agent.llm.close()
