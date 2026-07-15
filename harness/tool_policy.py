"""Per-turn tool selection for models with very different context budgets.

Tool schemas are instructions too. Sending every capability on every request
costs context and makes small models choose poorly. This module exposes the
smallest useful, stable tool set for a turn while keeping capability discovery
available through ``skill`` and ``mcp``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


FILE_TOOLS = {"read_file", "list_dir", "search"}
CODE_TOOLS = FILE_TOOLS | {"write_file", "edit_file", "run"}


@dataclass(frozen=True)
class ToolPolicy:
    profile: str
    names: frozenset[str]
    skill_limit: int
    skill_chars: int
    project_chars: int
    catalog_detail: str


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.DOTALL) is not None


def select_tool_policy(text: str, context_window: int) -> ToolPolicy:
    """Select a deterministic tool set once at the beginning of a turn."""
    low = " ".join(text.split())
    if context_window <= 4096:
        profile, skill_limit, skill_chars, project_chars, detail = (
            "compact", 1, 1800, 1200, "topics")
    elif context_window <= 8192:
        profile, skill_limit, skill_chars, project_chars, detail = (
            "lean", 2, 3600, 2500, "names")
    elif context_window <= 16384:
        profile, skill_limit, skill_chars, project_chars, detail = (
            "balanced", 3, 7500, 4500, "names")
    else:
        profile, skill_limit, skill_chars, project_chars, detail = (
            "full", 3, 16000, 6000, "names")

    names = {"skill"}
    code = _has(
        low,
        r"\b(code|coding|implement|fix|debug|bug|test|build|repo(?:sitory)?|"
        r"codebase|file|folder|script|package|dependency|git|html|css|"
        r"javascript|typescript|python|rust|java|backend|frontend|"
        r"harness|terminal|shell|command|cli|refactor|audit)\b",
    )
    file_work = code or _has(
        low, r"\b(read|inspect|edit|write|create|save|open|analy[sz]e)\b.{0,35}"
        r"\b(file|document|pdf|image|spreadsheet|presentation)\b")
    office = _has(low, r"\b(docx|word document|pdf|xlsx|xls|spreadsheet|excel|"
                  r"csv|pptx|powerpoint|slide deck|presentation)\b")
    creative_build = _has(
        low, r"\b(blender|three\.?js|webgl|3d (?:model|scene|animation)|"
        r"canvas game|browser game|godot|gdscript)\b")
    visual = _has(
        low, r"\b(ui|ux|html|css|frontend|web ?page|website|layout|responsive|"
        r"visual|screenshot|render|canvas|three\.?js|webgl)\b")
    web = _has(
        low, r"\b(web|internet|online|search the web|look up|latest|current|"
        r"source|citation|url|website|web ?page|browser)\b")
    interactive_browser = _has(
        low, r"\b(browser|chrome|firefox|edge|website|web ?app|gmail)\b.{0,100}"
        r"\b(open|navigate|click|type|submit|sign ?in|log ?in|interact)\b|"
        r"\b(open|navigate|click|type|submit|sign ?in|log ?in|interact)\b"
        r".{0,100}\b(browser|chrome|firefox|edge|website|web ?app|gmail)\b")
    computer = _has(
        low, r"\b(desktop app|computer use|mouse|keyboard|screen|window|"
        r"native app|microsoft (?:word|excel|powerpoint)|finder|file explorer)\b|"
        r"\b(?:existing|signed[- ]in|my)\b.{0,30}\b(?:chrome|browser|app)\b")
    mcp = _has(low, r"\b(mcp|connector|plugin|external tool|tool server)\b")
    memory = _has(low, r"\b(remember|memory|preference|past (?:chat|session)|history)\b")
    learning = _has(low, r"\b(save|create|update|learn).{0,20}\bskill\b")
    delegation = _has(low, r"\b(subtask|delegate|parallel|helper agent|subagent)\b")

    if code or creative_build:
        names |= CODE_TOOLS
    elif office:
        names |= CODE_TOOLS
    elif file_work:
        names |= FILE_TOOLS | {"write_file", "edit_file"}
    if visual:
        names.add("visual_check")
        names |= FILE_TOOLS
    if web:
        names |= {"web_search", "fetch"}
    if interactive_browser:
        names.add("browser")
    if computer:
        names.add("computer")
    if mcp:
        names.add("mcp")
    if memory:
        names |= {"remember", "history_search"}
    if learning:
        names.add("save_skill")
    if delegation and context_window > 8192:
        names.add("subtask")

    # Medium/large models get cheap escape hatches without receiving the two
    # very large GUI schemas unless the request actually needs them.
    if profile in {"balanced", "full"}:
        names |= {"mcp", "history_search"}
    if profile == "full":
        names |= {"remember", "save_skill"}
        if code:
            names.add("subtask")

    # An action request with no clear domain still needs a practical core.
    action = _has(low, r"\b(make|create|change|update|do|help|work on|analy[sz]e)\b")
    if action and len(names) == 1:
        names |= FILE_TOOLS

    return ToolPolicy(
        profile=profile,
        names=frozenset(names),
        skill_limit=skill_limit,
        skill_chars=skill_chars,
        project_chars=project_chars,
        catalog_detail=detail,
    )


def tool_guide(names: set[str] | frozenset[str]) -> str:
    """Short prompt guidance only for capabilities the model can actually see."""
    lines = ["Available tools are intentionally scoped to this turn."]
    if names & CODE_TOOLS:
        lines.append("For local work, inspect first, make focused changes, then run relevant checks.")
    if "visual_check" in names:
        lines.append("For changed UI, visual_check desktop/mobile and important interactive states before finishing.")
    if "browser" in names:
        lines.append("Browser: get fresh state, use only current refs, and verify after each action.")
    if "computer" in names:
        lines.append("Computer: open/list apps, get_state, then use exact current numeric element IDs.")
    if "mcp" in names:
        lines.append("MCP: search by capability, then call the exact returned tool name.")
    if "skill" in names:
        lines.append("Skills: search when needed, load once, then follow the active instructions.")
    return "\n".join(f"- {line}" for line in lines)
