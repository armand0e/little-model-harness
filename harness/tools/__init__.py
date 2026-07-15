"""Core tool registry.

Design rule for small models: FEW tools, SHORT schemas, ONE obvious way to
do each thing. Specialized capabilities live in skills (instructions +
helper scripts run through `run`), not in extra tool schemas.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from .files import read_file, write_file, edit_file, list_dir, search
from .shell import run_command
from .web import fetch_url, web_search

MAX_DIRECT_MCP_TOOLS = 24
MAX_DIRECT_MCP_SCHEMA_CHARS = 12_000

_COMPUTER_LAYOUT_PREFIXES = (
    "window ", "pane ", "region ", "group ", "separator ",
    "tool bar ", "graphic ",
)


def _computer_element_line(line: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*(\d+)\s+(.+?)\s*$", line)
    return (match.group(1), match.group(2)) if match else None


def _computer_layout_line(body: str) -> bool:
    lowered = body.casefold()
    return any(lowered.startswith(prefix) for prefix in _COMPUTER_LAYOUT_PREFIXES)


def _clean_computer_element(element_id: str, body: str) -> str:
    body = re.sub(r"\s+Frame:\s+\{.*$", "", body)
    action_match = re.search(r"\s+Secondary Actions:\s+(.+)$", body)
    if action_match:
        actions = [item.strip() for item in action_match.group(1).split(",")]
        actions = [item for item in actions if item != "ScrollIntoView"]
        body = body[:action_match.start()]
        if actions:
            body += " Actions: " + ", ".join(actions)
    return f"{element_id} {body.strip()}"


def _compact_computer_report(report: str) -> str:
    """Remove UIA layout noise while retaining exact native element IDs."""
    if report.lstrip().startswith("Error"):
        return report
    headers: list[str] = []
    elements: list[str] = []
    notes: list[str] = []
    for raw_line in report.splitlines():
        parsed = _computer_element_line(raw_line)
        if parsed:
            element_id, body = parsed
            if not _computer_layout_line(body):
                elements.append(_clean_computer_element(element_id, body))
        elif raw_line.startswith(("App=", "Window:")):
            headers.append(raw_line)
        elif raw_line.startswith(("Selected text:", "The focused UI element",
                                  "The current app screenshot")):
            notes.append(raw_line)
    if not elements:
        return report
    return "\n".join([
        *headers,
        "Actionable/content elements (use these exact numeric IDs):",
        *elements,
        *notes,
    ])


def _find_computer_elements(report: str, query: str,
                            limit: int = 12) -> list[str]:
    phrase = query.strip().casefold()
    terms = phrase.split()
    if not terms:
        return []
    matches: list[tuple[int, int, str]] = []
    for raw_line in report.splitlines():
        parsed = _computer_element_line(raw_line)
        if not parsed:
            continue
        element_id, body = parsed
        if _computer_layout_line(body):
            continue
        haystack = body.casefold()
        if not all(term in haystack for term in terms):
            continue
        score = (100 if phrase in haystack else 0)
        if any(action in haystack for action in (
                "actions: invoke", "actions: toggle", "actions: select",
                "actions: expand", "actions: setvalue")):
            score += 30
        if re.search(rf"^(?:\S+\s+){{0,3}}{re.escape(phrase)}(?:\s|$)",
                     haystack):
            score += 50
        matches.append((-score, len(body),
                        _clean_computer_element(element_id, body)))
    matches.sort()
    return [line for _, _, line in matches[:limit]]


def _context_bounded_mcp_schemas(schemas: list[dict]) -> list[dict]:
    """Expose a useful direct subset; the generic MCP tool reaches the rest."""
    selected: list[dict] = []
    chars = 0
    for schema in schemas:
        encoded = json.dumps(schema, ensure_ascii=False)
        if (len(selected) >= MAX_DIRECT_MCP_TOOLS
                or chars + len(encoded) > MAX_DIRECT_MCP_SCHEMA_CHARS):
            break
        selected.append(schema)
        chars += len(encoded)
    return selected


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict, Callable]] = {}

    def register(self, schema: dict, fn: Callable) -> None:
        self._tools[schema["name"]] = (
            {"type": "function", "function": schema}, fn)

    def schemas(self) -> list[dict]:
        from ..mcp_client import MCP_HUB
        return ([s for s, _ in self._tools.values()]
                + _context_bounded_mcp_schemas(
                    MCP_HUB.schemas(include_builtin=False)))

    def execute(self, name: str, arguments: str, agent=None) -> str:
        if name not in self._tools:
            from ..mcp_client import MCP_HUB
            if MCP_HUB.has_tool(name):
                try:
                    args = json.loads(arguments) if arguments.strip() else {}
                except json.JSONDecodeError as e:
                    return f"Error: MCP tool arguments were not valid JSON ({e})."
                if not isinstance(args, dict):
                    return "Error: MCP tool arguments must be a JSON object."
                return MCP_HUB.call(
                    name, args, stop_event=getattr(agent, "_stop", None))
            known = ", ".join(self._tools)
            return f"Error: unknown tool '{name}'. Available tools: {known}"
        _, fn = self._tools[name]
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as e:
            return f"Error: tool arguments were not valid JSON ({e}). Retry with valid JSON."
        if not isinstance(args, dict):
            return "Error: tool arguments must be a JSON object."
        try:
            if fn.__code__.co_varnames[:1] == ("agent",):
                return fn(agent, **args)
            return fn(**args)
        except TypeError as e:
            return f"Error: bad arguments for {name}: {e}"
        except Exception as e:
            return f"Error running {name}: {type(e).__name__}: {e}"


def build_registry(skills_manager) -> ToolRegistry:
    reg = ToolRegistry()

    def _ws(agent):
        """The chat's workspace — base dir for relative paths and `run`."""
        return getattr(agent, "workspace", None)

    def read_file_t(agent, path: str, start_line: int = 1,
                    max_lines: int = 200) -> str:
        return read_file(path, start_line, max_lines, base=_ws(agent))

    reg.register({
        "name": "read_file",
        "description": "Read a file. Text returns numbered lines; images (png/jpg/...) are shown to you; PDFs are shown as page images (start_line=first page, max_lines=page count).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer", "description": "1-based, default 1"},
            "max_lines": {"type": "integer", "description": "default 200"},
        }, "required": ["path"]},
    }, read_file_t)

    def write_file_checked(agent, path: str, content: str) -> str:
        checkpoint_count = len(agent.checkpoints) if agent is not None else 0
        snapshot_ok = (agent.record_file_snapshot(path)
                       if agent is not None else True)
        try:
            result = write_file(path, content, base=_ws(agent))
        except BaseException:
            if agent is not None:
                del agent.checkpoints[checkpoint_count:]
            raise
        result = _with_check(path, result, _ws(agent))
        if not snapshot_ok and not result.startswith("Error"):
            result += ("\nWarning: the previous file was too large or unreadable "
                       "to checkpoint, so chat revert cannot restore it.")
        return result

    def edit_file_checked(agent, path: str, old_text: str, new_text: str) -> str:
        checkpoint_count = len(agent.checkpoints) if agent is not None else 0
        snapshot_ok = (agent.record_file_snapshot(path)
                       if agent is not None else True)
        try:
            result = edit_file(path, old_text, new_text, base=_ws(agent))
        except BaseException:
            if agent is not None:
                del agent.checkpoints[checkpoint_count:]
            raise
        if result.startswith("Error") and agent is not None:
            del agent.checkpoints[checkpoint_count:]
        result = _with_check(path, result, _ws(agent))
        if not snapshot_ok and not result.startswith("Error"):
            result += ("\nWarning: the previous file was too large or unreadable "
                       "to checkpoint, so chat revert cannot restore it.")
        return result

    def _with_check(path: str, result: str, base) -> str:
        if result.startswith("Error"):
            return result
        from ..verify import check_written_file
        from .files import _resolve
        report = check_written_file(_resolve(path, base), visual_root=base)
        if report and report.startswith("__VISUAL_QA__:"):
            try:
                payload = json.loads(report[len("__VISUAL_QA__:"):])
                payload["report"] = result + "\n" + str(payload.get("report", ""))
                return "__VISUAL_QA__:" + json.dumps(payload, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                return result + "\nVisual QA returned malformed evidence; re-run visual_check."
        return f"{result}\n{report}" if report else result

    reg.register({
        "name": "write_file",
        "description": "Create or overwrite a file. HTML is rendered at desktop/mobile sizes and its screenshots are shown to you; Python/JS gets syntax checks. Inspect verification results and fix issues.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        }, "required": ["path", "content"]},
    }, write_file_checked)

    reg.register({
        "name": "edit_file",
        "description": "Replace an exact text snippet in a file with new text. The snippet must appear exactly once.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        }, "required": ["path", "old_text", "new_text"]},
    }, edit_file_checked)

    def visual_check_t(agent, target: str, viewports: str = "desktop,tablet,mobile",
                       click_selector: str = "", scroll_selector: str = "",
                       state_label: str = "default", wait_ms: int = 700,
                       full_page: bool = False) -> str:
        from urllib.parse import urlsplit
        from ..verify import visual_check
        from .files import _resolve
        workspace = _ws(agent)
        parsed = urlsplit(target)
        resolved = (target if parsed.scheme in {"http", "https"}
                    else _resolve(target, workspace))
        return visual_check(
            resolved, workspace, viewports=viewports,
            click_selector=click_selector, scroll_selector=scroll_selector,
            state_label=state_label, wait_ms=wait_ms, full_page=full_page)

    reg.register({
        "name": "visual_check",
        "description": "Visually verify local HTML or a localhost UI. Captures and shows screenshots at desktop/tablet/mobile sizes plus console, broken-image, and overflow diagnostics. Use after UI work; call again with click_selector/state_label for menus, modals, or other important states.",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "description": "HTML path or localhost URL"},
            "viewports": {"type": "string", "description": "comma list: desktop,tablet,mobile"},
            "click_selector": {"type": "string", "description": "optional CSS selector to click first"},
            "scroll_selector": {"type": "string", "description": "optional CSS selector to scroll into view"},
            "state_label": {"type": "string", "description": "screenshot label, e.g. modal-open"},
            "wait_ms": {"type": "integer", "description": "settle time after interaction, default 700"},
            "full_page": {"type": "boolean", "description": "capture full page instead of viewport"},
        }, "required": ["target"]},
    }, visual_check_t)

    def list_dir_t(agent, path: str = ".") -> str:
        return list_dir(path, base=_ws(agent))

    reg.register({
        "name": "list_dir",
        "description": "List files and folders in a directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "default: working directory"},
        }},
    }, list_dir_t)

    def search_t(agent, glob: str = "", text: str = "", path: str = ".") -> str:
        return search(glob, text, path, base=_ws(agent))

    reg.register({
        "name": "search",
        "description": "Find files by name pattern (glob like **/*.py) and/or search file contents for text.",
        "parameters": {"type": "object", "properties": {
            "glob": {"type": "string", "description": "filename pattern"},
            "text": {"type": "string", "description": "text to find inside files"},
            "path": {"type": "string", "description": "directory to search, default: working directory"},
        }},
    }, search_t)

    def run_t(agent, command: str, timeout_seconds: int = 60) -> str:
        return run_command(
            command, timeout_seconds, cwd=_ws(agent),
            stop_event=getattr(agent, "_stop", None),
        )

    reg.register({
        "name": "run",
        "description": "Run a PowerShell command and return its output. It runs in your working directory. Use for shell tasks and to run skill helper scripts.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout_seconds": {"type": "integer", "description": "default 60"},
        }, "required": ["command"]},
    }, run_t)

    reg.register({
        "name": "web_search",
        "description": "Search the web. Returns titles, URLs and snippets.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
        }, "required": ["query"]},
    }, web_search)

    reg.register({
        "name": "fetch",
        "description": "Fetch a web page as readable plain text.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }, fetch_url)

    computer_ready_apps: set[str] = set()
    computer_current_app: str | None = None
    computer_last_reports: dict[str, str] = {}

    def computer_tool(action: str, app: str | None = None,
                      element: str | None = None, text: str | None = None,
                      query: str | None = None,
                      key: str | None = None, direction: str | None = None,
                      pages: float | None = None, x: float | None = None,
                      y: float | None = None, to_x: float | None = None,
                      to_y: float | None = None, button: str | None = None,
                      clicks: int | None = None,
                      secondary_action: str | None = None) -> str:
        """Small-model-friendly facade over the bundled OS-native MCP."""
        nonlocal computer_current_app
        from ..mcp_client import MCP_HUB, computer_backend_info
        if action == "open_app":
            if not app:
                return "Error: computer action 'open_app' requires app."
            import os
            import platform
            import subprocess
            import time
            try:
                computer_ready_apps.discard(app.casefold())
                system = platform.system()
                if system == "Windows":
                    try:
                        os.startfile(app)  # type: ignore[attr-defined]  # noqa: S606
                    except OSError:
                        env = {**os.environ, "LMH_OPEN_TARGET": app}
                        subprocess.Popen(
                            ["powershell", "-NoProfile", "-Command",
                             "Start-Process -FilePath $env:LMH_OPEN_TARGET"],
                            env=env,
                            creationflags=0x08000000,
                        )
                elif system == "Darwin":
                    command = (["open", app] if "://" in app or os.path.exists(app)
                               else ["open", "-a", app])
                    subprocess.Popen(command)
                else:
                    import shutil
                    resolved = shutil.which(app)
                    subprocess.Popen([resolved] if resolved
                                     else ["xdg-open", app])
                time.sleep(0.6)
                computer_current_app = app
                return (f"Opened {app}. Use list_apps if its runtime name is "
                        "unclear, then get_state before interacting.")
            except Exception as exc:
                return f"Error opening {app}: {type(exc).__name__}: {exc}"
        tools = {
            "list_apps": "list_apps", "get_state": "get_app_state", "find": "",
            "click": "click", "set_value": "set_value",
            "type_text": "type_text", "press_key": "press_key",
            "scroll": "scroll", "drag": "drag",
            "focus": "perform_secondary_action",
            "secondary_action": "perform_secondary_action",
        }
        original = tools.get(action)
        if original is None:
            return f"Error: unknown computer action {action!r}."
        if action != "list_apps" and not app:
            app = computer_current_app
        app_key = (app or "").casefold()
        if action == "find":
            if not app:
                return "Error: computer action 'find' requires an active app."
            if not query:
                return "Error: computer action 'find' requires query."
            cached_report = computer_last_reports.get(app_key)
            if cached_report is None:
                return (f"Error: call computer get_state successfully for {app!r} "
                        "before finding elements.")
            matches = _find_computer_elements(cached_report, query)
            if not matches:
                return f"No actionable/content elements matched {query!r} in {app}."
            return (f"Matches for {query!r} in {app}; use the exact numeric ID:\n"
                    + "\n".join(matches))
        info = computer_backend_info()
        if not info["available"]:
            return ("Error: native computer control is unavailable in this "
                    "source environment. Packaged builds include it; source "
                    "runs can set LMH_COMPUTER_USE_BIN.")
        public = f"computer_{original}"
        if not MCP_HUB.has_tool(public):
            return "Error: native computer control failed to start. Check MCP status."
        stateful_actions = {
            "click", "set_value", "type_text", "press_key", "scroll",
            "drag", "focus", "secondary_action",
        }
        if action in stateful_actions and app_key not in computer_ready_apps:
            return (f"Error: call computer get_state successfully for {app!r} "
                    "before interacting. Do not guess elements or retry the "
                    "same action after a state error.")
        if (action in {"click", "focus", "set_value", "scroll"}
                and element is None and query):
            matches = _find_computer_elements(
                computer_last_reports.get(app_key, ""), query, limit=1)
            if not matches:
                return f"Error: no actionable element matched query {query!r}."
            element = matches[0].split(" ", 1)[0]
        if action in {"focus", "set_value", "scroll", "secondary_action"} \
                and element is None:
            return f"Error: computer action {action!r} requires element."
        if (action == "click" and element is None
                and (x is None or y is None)):
            return "Error: computer click requires element, query, or x/y."
        if (element is not None and action in {
                "click", "set_value", "scroll", "focus", "secondary_action"}
                and not str(element).isdigit()):
            return ("Error: element must be the numeric semantic ID from the "
                    "latest successful get_state result, not a label or AX name.")
        if action == "click" and element is not None:
            chosen = next((parsed for line in computer_last_reports.get(
                app_key, "").splitlines()
                           if (parsed := _computer_element_line(line))
                           and parsed[0] == str(element)), None)
            if chosen and _computer_layout_line(chosen[1]):
                return (f"Error: element {element} is a layout container, not a "
                        "safe click target. Use computer find with a text query "
                        "and click the matching link, button, edit, or tab ID.")
        args: dict[str, object] = {}
        if action != "list_apps":
            if not app:
                return f"Error: computer action {action!r} requires app."
            args["app"] = app
        if element is not None:
            args["element_index"] = element
        if text is not None:
            args["text" if action == "type_text" else "value"] = text
        if key is not None:
            args["key"] = key
        if direction is not None:
            args["direction"] = direction
        if pages is not None:
            args["pages"] = pages
        if action == "drag":
            if None in {x, y, to_x, to_y}:
                return "Error: drag requires x, y, to_x, and to_y."
            args.update({"from_x": x, "from_y": y,
                         "to_x": to_x, "to_y": to_y})
        else:
            if x is not None:
                args["x"] = x
            if y is not None:
                args["y"] = y
        if button is not None:
            args["mouse_button"] = button
        if clicks is not None:
            args["click_count"] = clicks
        if secondary_action is not None:
            args["action"] = secondary_action
        if action == "focus":
            args["action"] = "SetFocus"
        result = MCP_HUB.call(public, args)
        tool_report: str = result
        marker_payload: dict | None = None
        if result.startswith("__MCP_IMAGE_RESULT__:"):
            try:
                decoded = json.loads(result.split(":", 1)[1])
                if not isinstance(decoded, dict):
                    raise TypeError("computer marker payload is not an object")
                marker_payload = decoded
                decoded_report = marker_payload.get("report", "")
                if not isinstance(decoded_report, str):
                    raise TypeError("computer marker report is not text")
                tool_report = decoded_report
            except (json.JSONDecodeError, TypeError, AttributeError):
                tool_report = "Error: malformed computer screenshot result."
                marker_payload = None
        if tool_report.lstrip().startswith("Error"):
            computer_ready_apps.discard(app_key)
        else:
            if action != "list_apps" and app:
                computer_last_reports[app_key] = tool_report
                compact_report = _compact_computer_report(tool_report)
                if marker_payload is not None:
                    marker_payload["report"] = compact_report
                    result = "__MCP_IMAGE_RESULT__:" + json.dumps(
                        marker_payload, separators=(",", ":"))
                else:
                    result = compact_report
            if action == "get_state":
                computer_ready_apps.add(app_key)
                computer_current_app = app
        return result

    reg.register({
        "name": "computer",
        "description": "Control desktop apps through the OS accessibility tree. Open if needed, then get_state. Use find/query for named targets (for example Gmail) instead of scanning or guessing IDs; click only exact link/button/edit/tab IDs. Action results include updated state and screenshots.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["open_app", "list_apps", "get_state", "find", "focus", "click", "set_value", "type_text", "press_key", "scroll", "drag", "secondary_action"]},
            "app": {"type": "string", "description": "app name from list_apps; optional after open_app or a successful get_state because the active app is remembered"},
            "element": {"type": "string", "description": "semantic element ID from get_state"},
            "query": {"type": "string", "description": "visible name/label to find, or resolve automatically for click/focus/set_value/scroll"},
            "text": {"type": "string", "description": "text/value for type_text or set_value"},
            "key": {"type": "string", "description": "key combo, e.g. ctrl+s or Return"},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
            "pages": {"type": "number"},
            "x": {"type": "number"}, "y": {"type": "number"},
            "to_x": {"type": "number"}, "to_y": {"type": "number"},
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
            "clicks": {"type": "integer"},
            "secondary_action": {"type": "string"},
        }, "required": ["action"]},
    }, computer_tool)

    def mcp_tool(agent, action: str, query: str | None = None,
                 tool: str | None = None,
                 arguments: dict | None = None) -> str:
        """Progressive discovery/call facade for large MCP catalogs."""
        from ..mcp_client import MCP_HUB
        if action == "search":
            return MCP_HUB.search(query or "")
        if action == "call":
            if not tool:
                return "Error: mcp action 'call' requires tool."
            if not MCP_HUB.is_user_tool(tool):
                return ("Error: that user MCP tool is unavailable. Search for "
                        "its exact public name first.")
            if arguments is not None and not isinstance(arguments, dict):
                return "Error: mcp arguments must be an object."
            return MCP_HUB.call(
                tool, arguments or {},
                stop_event=getattr(agent, "_stop", None),
            )
        return "Error: mcp action must be 'search' or 'call'."

    reg.register({
        "name": "mcp",
        "description": "Search and call user-configured MCP tools that are not directly listed because tool schemas consume context. Use search with a capability phrase, then call the exact returned tool name.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["search", "call"]},
            "query": {"type": "string", "description": "capability to find"},
            "tool": {"type": "string", "description": "exact public MCP tool name"},
            "arguments": {"type": "object", "description": "arguments for the MCP tool"},
        }, "required": ["action"]},
    }, mcp_tool)

    def load_skill(name: str) -> str:
        return skills_manager.load(name)

    reg.register({
        "name": "skill",
        "description": "Load instructions for a relevant skill that was not already auto-loaded. Call before that specialized work, once per skill per turn.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "skill name from the list in the system prompt"},
        }, "required": ["name"]},
    }, load_skill)

    def save_skill_tool(agent, name: str, hint: str, content: str,
                        category: str | None = None, append: bool = False) -> str:
        from ..skills import save_skill, user_skill_file
        if agent is not None:
            # Learned skills participate in chat revert like file edits do.
            agent.record_file_snapshot(str(user_skill_file(name)))
        result = save_skill(name, hint, content, category, append)
        if agent is not None and not result.startswith("Error"):
            agent.skills.refresh()
        return result

    reg.register({
        "name": "save_skill",
        "description": "Save what you learned as a skill (or extend one with append=true) so future sessions know it. Use after solving something nontrivial or discovering an API/tool gotcha.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "kebab-case skill name (existing or new)"},
            "hint": {"type": "string", "description": "<=10 word index line"},
            "content": {"type": "string", "description": "the instructions/facts, markdown"},
            "category": {"type": "string", "description": "office|software|writing|reasoning|math|science|creative|other"},
            "append": {"type": "boolean", "description": "true = add to existing skill body"},
        }, "required": ["name", "hint", "content"]},
    }, save_skill_tool)

    def remember_tool(agent, fact: str) -> str:
        from ..config import MEMORY_FILE
        from ..memory import remember
        if agent is not None:
            agent.record_file_snapshot(str(MEMORY_FILE))
        return remember(fact)

    reg.register({
        "name": "remember",
        "description": "Store one durable fact about the user, this machine, or preferences. It will be shown to you in every future session.",
        "parameters": {"type": "object", "properties": {
            "fact": {"type": "string", "description": "one short fact, <=300 chars"},
        }, "required": ["fact"]},
    }, remember_tool)

    def history_tool(query: str) -> str:
        from ..memory import search_sessions
        return search_sessions(query)

    reg.register({
        "name": "history_search",
        "description": "Search past chat sessions for how something was done before.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "a few keywords"},
        }, "required": ["query"]},
    }, history_tool)

    def todo_tool(agent, items: list) -> str:
        if not isinstance(items, list) or not items:
            return "Error: todo requires a non-empty items array."
        if len(items) > 12:
            return "Error: keep the todo list to 12 items or fewer."
        marks = {"pending": "[ ]", "active": "[>]", "done": "[x]"}
        lines = []
        for item in items:
            if not isinstance(item, dict):
                return "Error: each todo item must be {text, status}."
            text = " ".join(str(item.get("text", "")).split())[:120]
            status = str(item.get("status", "pending"))
            if not text or status not in marks:
                return ("Error: each item needs text and a status of "
                        "pending, active, or done.")
            lines.append(f"{marks[status]} {text}")
        remaining = sum(1 for line in lines if not line.startswith("[x]"))
        return ("Task list updated"
                + (f" — {remaining} remaining" if remaining else " — all done")
                + ":\n" + "\n".join(lines))

    reg.register({
        "name": "todo",
        "description": "Maintain your visible task checklist for this request. Send the FULL updated list each time (3-8 short items). Statuses: pending, active (what you are doing now), done. Update it as you finish each step.",
        "parameters": {"type": "object", "properties": {
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "active", "done"]},
            }, "required": ["text", "status"]}},
        }, "required": ["items"]},
    }, todo_tool)

    def subtask_tool(agent, task: str) -> str:
        if agent is None:
            return "Error: subtask unavailable here."
        return agent.run_subtask(task)

    reg.register({
        "name": "subtask",
        "description": "Run an isolated helper agent with a FRESH context on a self-contained task (research, exploring many files, drafting). You get only its final summary — use it to keep long digressions out of your context. Give it complete instructions; it can't see this conversation.",
        "parameters": {"type": "object", "properties": {
            "task": {"type": "string", "description": "full standalone instructions incl. relevant paths"},
        }, "required": ["task"]},
    }, subtask_tool)

    return reg
