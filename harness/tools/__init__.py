"""Core tool registry.

Design rule for small models: FEW tools, SHORT schemas, ONE obvious way to
do each thing. Specialized capabilities live in skills (instructions +
helper scripts run through `run`), not in extra tool schemas.
"""
from __future__ import annotations

import json
from typing import Callable

from .files import read_file, write_file, edit_file, list_dir, search
from .shell import run_command
from .web import fetch_url, web_search


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict, Callable]] = {}

    def register(self, schema: dict, fn: Callable) -> None:
        self._tools[schema["name"]] = (
            {"type": "function", "function": schema}, fn)

    def schemas(self) -> list[dict]:
        return [s for s, _ in self._tools.values()]

    def execute(self, name: str, arguments: str, agent=None) -> str:
        if name not in self._tools:
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
        if agent is not None:
            agent.record_file_snapshot(path)
        result = write_file(path, content, base=_ws(agent))
        return _with_check(path, result, _ws(agent))

    def edit_file_checked(agent, path: str, old_text: str, new_text: str) -> str:
        if agent is not None:
            agent.record_file_snapshot(path)
        result = edit_file(path, old_text, new_text, base=_ws(agent))
        return _with_check(path, result, _ws(agent))

    def _with_check(path: str, result: str, base) -> str:
        if result.startswith("Error"):
            return result
        from ..verify import check_written_file
        from .files import _resolve
        report = check_written_file(_resolve(path, base))
        return f"{result}\n{report}" if report else result

    reg.register({
        "name": "write_file",
        "description": "Create or overwrite a file with the given content. Saved .py/.js/.html files are auto-checked and errors reported back.",
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
        return run_command(command, timeout_seconds, cwd=_ws(agent))

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

    def load_skill(name: str) -> str:
        return skills_manager.load(name)

    reg.register({
        "name": "skill",
        "description": "Load the instructions for a skill before doing that kind of task. Call once per skill.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "skill name from the list in the system prompt"},
        }, "required": ["name"]},
    }, load_skill)

    def save_skill_tool(agent, name: str, hint: str, content: str,
                        category: str = "other", append: bool = False) -> str:
        from ..skills import save_skill
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

    def remember_tool(fact: str) -> str:
        from ..memory import remember
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
