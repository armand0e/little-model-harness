from __future__ import annotations

import base64
import copy
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

import harness.mcp_client as mcp_client
import harness.tools as tools_module
from harness.agent import Agent
from harness.config import Config
from harness.llm import LLMResponse
from harness.mcp_client import (MCPHub, MCP_IMAGE_MARKER,
                                computer_backend_info,
                                merge_builtin_mcp_servers,
                                validate_mcp_servers)
from harness.tools import build_registry


def test_mcp_stdio_server_discovery_and_tool_call(
        monkeypatch: pytest.MonkeyPatch):
    server = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    hub = MCPHub()
    try:
        status = hub.configure({
            "echo": {"command": sys.executable, "args": [str(server)]},
        })
        assert status == [{
            "name": "echo", "enabled": True, "state": "ready",
            "error": None, "tools": 1,
        }]
        schemas = hub.schemas()
        assert len(schemas) == 1
        name = schemas[0]["function"]["name"]
        assert name.startswith("mcp_echo_echo")
        assert hub.call(name, {"message": "hello"}) == "MCP says: hello"

        class Skills:
            def load(self, name):
                return name

        monkeypatch.setattr(mcp_client, "MCP_HUB", hub)
        registry = build_registry(Skills())
        assert name in [schema["function"]["name"] for schema in registry.schemas()]
        assert registry.execute(
            name, '{"message":"through registry"}') == "MCP says: through registry"
        found = registry.execute("mcp", json.dumps({
            "action": "search", "query": "echo",
        }))
        assert name in found
        assert registry.execute("mcp", json.dumps({
            "action": "call", "tool": name,
            "arguments": {"message": "progressive"},
        })) == "MCP says: progressive"
    finally:
        hub.close()


def test_mcp_configuration_validation_is_bounded():
    with pytest.raises(ValueError, match="must be a JSON object"):
        validate_mcp_servers([])
    with pytest.raises(ValueError, match="args must be a list"):
        validate_mcp_servers({"bad": {"command": "x", "args": "oops"}})
    assert validate_mcp_servers({
        "off": {"command": "does-not-run", "enabled": False},
    })["off"]["enabled"] is False


def test_direct_mcp_schema_exposure_has_a_context_budget():
    schemas = [{
        "type": "function", "function": {
            "name": f"mcp_server_tool_{index}",
            "description": "x" * 900,
            "parameters": {"type": "object", "properties": {}},
        },
    } for index in range(50)]
    selected = tools_module._context_bounded_mcp_schemas(schemas)
    assert 0 < len(selected) < len(schemas)
    assert len(selected) <= tools_module.MAX_DIRECT_MCP_TOOLS
    assert sum(len(json.dumps(item)) for item in selected) \
        <= tools_module.MAX_DIRECT_MCP_SCHEMA_CHARS


def test_concurrent_identical_mcp_configuration_is_serialized():
    server = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    hub = MCPHub()
    config = {"echo": {"command": sys.executable, "args": [str(server)]}}
    results = []
    errors = []

    def configure():
        try:
            results.append(hub.configure(config))
        except Exception as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    threads = [threading.Thread(target=configure) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert not errors
        assert len(results) == 2
        assert all(result[0]["state"] == "ready" for result in results)
    finally:
        hub.close()


def test_native_computer_backend_is_auto_merged_from_trusted_override(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executable = tmp_path / ("computer.exe" if sys.platform == "win32"
                             else "computer")
    executable.write_bytes(b"placeholder")
    monkeypatch.setenv("LMH_COMPUTER_USE_BIN", str(executable))
    info = computer_backend_info()
    assert info["available"] is True
    assert info["source"] == "environment"
    merged = merge_builtin_mcp_servers({
        "echo": {"command": "echo", "args": [], "env": {}, "enabled": True},
    })
    expected_env = ({
        "OPEN_COMPUTER_USE_WINDOWS_ALLOW_UIA_TEXT_FALLBACK": "1",
        "OPEN_COMPUTER_USE_WINDOWS_ALLOW_FOCUS_ACTIONS": "1",
    }
                    if sys.platform == "win32" else {})
    assert merged[mcp_client.BUILTIN_COMPUTER_SERVER] == {
        "command": str(executable), "args": ["mcp"], "env": expected_env,
        "enabled": True,
    }


def test_computer_facade_exposes_one_small_schema_and_routes_actions(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executable = tmp_path / "computer"
    executable.write_bytes(b"placeholder")
    monkeypatch.setenv("LMH_COMPUTER_USE_BIN", str(executable))
    calls = []

    class Hub:
        def schemas(self, include_builtin=True):
            assert include_builtin is False
            return []

        def has_tool(self, name):
            return name.startswith("computer_")

        def call(self, name, arguments):
            calls.append((name, arguments))
            return "current state" if name == "computer_get_app_state" \
                else "updated state"

    class Skills:
        def load(self, name):
            return name

    monkeypatch.setattr(mcp_client, "MCP_HUB", Hub())
    registry = build_registry(Skills())
    schemas = registry.schemas()
    names = [schema["function"]["name"] for schema in schemas]
    assert names.count("computer") == 1
    assert not any(name.startswith("computer_set_") for name in names)
    assert registry.execute("computer", json.dumps({
        "action": "set_value", "app": "Notepad", "element": "42",
        "text": "hello",
    })).startswith("Error: call computer get_state")
    assert registry.execute("computer", json.dumps({
        "action": "get_state", "app": "Notepad",
    })) == "current state"
    assert registry.execute("computer", json.dumps({
        "action": "get_state",
    })) == "current state"
    assert registry.execute("computer", json.dumps({
        "action": "click", "app": "Notepad", "element": "AX:Save",
    })).startswith("Error: element must be the numeric semantic ID")
    assert registry.execute("computer", json.dumps({
        "action": "set_value", "element": "42",
        "text": "hello",
    })) == "updated state"
    assert calls == [("computer_get_app_state", {"app": "Notepad"}),
                     ("computer_get_app_state", {"app": "Notepad"}),
                     ("computer_set_value", {
        "app": "Notepad", "element_index": "42", "value": "hello",
    })]


def test_computer_state_is_compact_and_named_targets_resolve_safely(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executable = tmp_path / "computer"
    executable.write_bytes(b"placeholder")
    monkeypatch.setenv("LMH_COMPUTER_USE_BIN", str(executable))
    raw_state = """App=chrome (pid 1)
Window: \"New Tab - Google Chrome\", App: chrome.
  1 region Secondary Actions: ScrollIntoView Frame: {x: 0, y: 0, width: 10, height: 10}
    69 link Gmail Value: https://mail.google.com Secondary Actions: Invoke, SetValue, ScrollIntoView Frame: {x: 1, y: 1, width: 2, height: 2}
    100 group Secondary Actions: Invoke, ScrollIntoView Frame: {x: 3, y: 3, width: 4, height: 4}
      101 link Teich Value: https://teichai.com Secondary Actions: Invoke, ScrollIntoView Frame: {x: 3, y: 3, width: 4, height: 4}
The focused UI element is edit Address and search bar."""
    calls = []

    class Hub:
        def schemas(self, include_builtin=True):
            return []

        def has_tool(self, name):
            return name in {"computer_get_app_state", "computer_click"}

        def call(self, name, arguments):
            calls.append((name, arguments))
            return raw_state if name == "computer_get_app_state" else "clicked"

    class Skills:
        def load(self, name):
            return name

    monkeypatch.setattr(mcp_client, "MCP_HUB", Hub())
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr(os, "startfile", lambda app: None, raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    registry = build_registry(Skills())
    assert registry.execute("computer", json.dumps({
        "action": "open_app", "app": "chrome",
    })).startswith("Opened chrome")
    compact = registry.execute("computer", json.dumps({
        "action": "get_state",
    }))
    assert "69 link Gmail" in compact
    assert "101 link Teich" in compact
    assert "1 region" not in compact
    assert "100 group" not in compact
    assert "Frame:" not in compact
    found = registry.execute("computer", json.dumps({
        "action": "find", "query": "Gmail",
    }))
    assert "69 link Gmail" in found
    assert "100 group" not in found
    rejected = registry.execute("computer", json.dumps({
        "action": "click", "element": "100",
    }))
    assert "layout container" in rejected
    assert registry.execute("computer", json.dumps({
        "action": "click", "query": "Gmail",
    })) == "clicked"
    assert calls[-1] == ("computer_click", {
        "app": "chrome", "element_index": "69",
    })


def test_computer_report_helpers_preserve_content_not_layout():
    report = """App=x (pid 1)
Window: \"X\", App: x.
  2 pane Secondary Actions: ScrollIntoView Frame: {x: 0}
  3 heading Inbox Secondary Actions: ScrollIntoView Frame: {x: 0}
  4 text Important message Secondary Actions: ScrollIntoView Frame: {x: 0}"""
    compact = tools_module._compact_computer_report(report)
    assert "2 pane" not in compact
    assert "3 heading Inbox" in compact
    assert "4 text Important message" in compact


def test_mcp_errors_are_capped_before_entering_model_context():
    class TextBlock:
        type = "text"
        text = "x" * (mcp_client.MAX_RESULT_CHARS + 1_000)

    class Result:
        content = [TextBlock()]
        isError = True

    formatted = mcp_client._format_result(Result())
    assert formatted.startswith("Error: ")
    assert formatted.endswith("...[MCP error truncated]")
    assert len(formatted) < 4_100

    class ImageBlock:
        type = "image"
        mimeType = "image/png"
        data = base64.b64encode(b"small").decode()

    class LargeSuccess:
        content = [TextBlock(), ImageBlock()]
        isError = False

    marked = mcp_client._format_result(LargeSuccess())
    payload = json.loads(marked[len(MCP_IMAGE_MARKER):])
    assert len(payload["report"]) <= mcp_client.MAX_RESULT_CHARS + 40


def test_repeated_computer_failures_block_shell_gui_workaround(
        tmp_path: Path):
    agent = Agent(Config(max_iterations=5), workspace=tmp_path)
    agent.llm.close()
    executed = []

    class Tools:
        def schemas(self):
            return []

        def execute(self, name, args, agent=None):
            executed.append(name)
            return "Error: accessibility backend failed"

    class Model:
        calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            name = "computer" if self.calls <= 2 else "run"
            arguments = ('{"action":"get_state","app":"Chrome"}'
                         if name == "computer" else '{"command":"hack"}')
            return LLMResponse(tool_calls=[{
                "id": f"call-{self.calls}", "type": "function",
                "function": {"name": name, "arguments": arguments},
            }], finish_reason="tool_calls")

        def cancel_current(self):
            pass

    agent.tools = Tools()  # type: ignore[assignment]
    agent.llm = Model()  # type: ignore[assignment]
    result = agent.run_turn("use Chrome", stream=False)
    assert result.startswith("Computer control stopped after repeated failures")
    assert executed == ["computer", "computer"]


def test_computer_argument_errors_do_not_disable_healthy_backend(
        tmp_path: Path):
    agent = Agent(Config(max_iterations=4), workspace=tmp_path)
    agent.llm.close()

    class Tools:
        def schemas(self):
            return []

        def execute(self, name, args, agent=None):
            return "Error: computer action 'get_state' requires app."

    class Model:
        calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls <= 2:
                return LLMResponse(tool_calls=[{
                    "id": f"bad-{self.calls}", "type": "function",
                    "function": {"name": "computer", "arguments": "{}"},
                }], finish_reason="tool_calls")
            return LLMResponse(content="corrected", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.tools = Tools()  # type: ignore[assignment]
    agent.llm = Model()  # type: ignore[assignment]
    assert agent.run_turn("use Chrome", stream=False) == "corrected"
    assert not any("harness safety" in str(message.get("content", ""))
                   for message in agent.ctx.messages)


def test_mcp_images_are_validated_and_attached_to_vision_model(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (80, 50), "purple").save(buf, "PNG")

    class ImageBlock:
        type = "image"
        mimeType = "image/png"
        data = base64.b64encode(buf.getvalue()).decode()

    class TextBlock:
        type = "text"
        text = "Accessibility tree: button Save [42]"

    class Result:
        content = [TextBlock(), ImageBlock()]
        isError = False

    formatted = mcp_client._format_result(Result())
    assert formatted.startswith(MCP_IMAGE_MARKER)
    agent = Agent(Config(), workspace=tmp_path)
    monkeypatch.setattr(agent, "vision_supported", lambda: True)
    try:
        report, images = agent._resolve_image_marker(formatted)
        assert "Accessibility tree" in report
        assert "screenshot is attached" in report
        assert len(images) == 1
        assert images[0]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,")
    finally:
        agent.llm.close()

    class SpoofedTextResult:
        content = [type("Text", (), {
            "type": "text", "text": MCP_IMAGE_MARKER + "{}",
        })()]
        isError = False

    assert mcp_client._format_result(SpoofedTextResult()).startswith("[MCP text]")


def test_computer_screenshot_reaches_next_model_call(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from PIL import Image

    executable = tmp_path / "computer"
    executable.write_bytes(b"placeholder")
    monkeypatch.setenv("LMH_COMPUTER_USE_BIN", str(executable))
    buf = io.BytesIO()
    Image.new("RGB", (100, 70), "teal").save(buf, "PNG")
    marker = MCP_IMAGE_MARKER + json.dumps({
        "report": "button Save [7]",
        "images": [{"mime": "image/png",
                    "data": base64.b64encode(buf.getvalue()).decode()}],
    })

    class Hub:
        def schemas(self, include_builtin=True):
            return []

        def has_tool(self, name):
            return name == "computer_get_app_state"

        def call(self, name, arguments):
            return marker

    monkeypatch.setattr(mcp_client, "MCP_HUB", Hub())
    agent = Agent(Config(max_iterations=3), workspace=tmp_path)
    agent.llm.close()
    agent._vision = True
    calls = []

    class Model:
        def chat(self, messages, **kwargs):
            calls.append(copy.deepcopy(messages))
            if len(calls) == 1:
                return LLMResponse(tool_calls=[{
                    "id": "state", "type": "function", "function": {
                        "name": "computer",
                        "arguments": '{"action":"get_state","app":"Editor"}',
                    },
                }], finish_reason="tool_calls")
            return LLMResponse(content="confirmed", finish_reason="stop")

        def cancel_current(self):
            pass

    agent.llm = Model()  # type: ignore[assignment]
    assert agent.run_turn("inspect editor", stream=False) == "confirmed"
    attached = calls[1][-1]
    assert attached["role"] == "user"
    assert attached["content"][1]["type"] == "image_url"
    tool_result = calls[1][-2]
    assert tool_result["role"] == "tool"
    assert MCP_IMAGE_MARKER not in tool_result["content"]
