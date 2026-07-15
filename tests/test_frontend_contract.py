from __future__ import annotations

import re
from pathlib import Path


UI = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(
    encoding="utf-8")


def test_frontend_uses_only_app_native_dialogs() -> None:
    script = UI.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert not re.search(r"(?<![A-Za-z])(?:alert|confirm|prompt)\s*\(", script)
    assert "Notification.requestPermission" not in script
    for marker in (
        'id="appdialogoverlay"',
        'id="appdialoginput"',
        "function appDialog(",
        "async function appConfirm(",
        "async function appPrompt(",
    ):
        assert marker in UI


def test_chat_and_code_histories_are_scoped_independently() -> None:
    assert 'id="historyscope">Code history' in UI
    assert 'const modeSessions = mode => sessions.filter' in UI
    assert ("const scopedSessions = "
            "projectScoped(modeSessions(renderedMode))") in UI
    assert ("results = projectScoped(\n"
            "        results.filter(session => sessionMode(session)"
            " === renderedMode))") in UI
    assert "lmh-last-session:${mode}" in UI
    assert "new:${draftMode}" in UI
    switch = UI.split("async function setConversationMode(mode)", 1)[1].split(
        "document.querySelectorAll", 1)[0]
    assert 'method: "PATCH"' not in switch
    assert "newChat();" in switch


def test_stop_generation_is_visible_and_error_aware() -> None:
    stop = UI.split("async function stopGeneration()", 1)[1].split(
        "function handleTurnEvent", 1)[0]
    assert "stoppingSessions.add(sid)" in stop
    assert 'await post(`/sessions/${sid}/stop`)' in stop
    assert 'appAlert("Could not stop generation"' in stop
    assert '$("stopbtn").onclick = stopGeneration' in UI
    assert "e.preventDefault(); stopGeneration();" in UI


def test_desktop_shell_has_custom_window_chrome() -> None:
    for marker in (
        'id="windowbar"', 'class="window-drag pywebview-drag-region"',
        'id="windowmin"', 'id="windowmax"', 'id="windowclose"',
        'callWindow("toggle_maximize")',
    ):
        assert marker in UI


def test_tool_errors_expand_and_successes_collapse() -> None:
    finish = UI.split("function finishTool(card, result)", 1)[1].split(
        "function addLoadedSkill", 1)[0]
    assert 'card.open = isErr;' in finish


def test_context_meter_reports_compaction_pressure_and_breakdown() -> None:
    update = UI.split("function updateCtx(ctx)", 1)[1].split(
        "/* ---------------- attachments", 1)[0]
    assert "ctx.compact_threshold" in update
    assert "ctx.estimated_tokens || ctx.last_prompt_tokens" in update
    assert "Post-compaction target" in update
    assert "ctx.tool_schema_tokens" in update
    assert 'document.querySelector(".ctxrow").title = breakdown;' in update
