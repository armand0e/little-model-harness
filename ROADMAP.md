# Rebuild roadmap

Main was reset to the v1.1.1 baseline on 2026-07-15 because the v2.x line
degraded agent behavior and the Qt port degraded the UI. The entire v2.x
history is preserved on the `v2-archive` branch. Features return one at a
time, each verified against the bar that v1.1.1 set: the agent must act
well, and the UI must feel like the web client.

**UI direction:** the web client (`web/index.html`) is the product UI,
wrapped by the Electron shell in `electron/` (`npm start`). The Qt client
exists only on `v2-archive`. UI work happens in the web client so the
browser and desktop stay one codebase.

## Reimplemented

- [x] **Deep research mode** — `harness/research.py` pipeline (scope →
  search/triage/fetch/extract rounds → reflection → cited report), the
  `research` session mode, and a third sidebar space in the web UI.
  Ported from v2 without touching the v1.1.1 agent loop or prompts.
- [x] **Electron shell** — sandboxed window over the Python sidecar
  (`--server-only`), sidecar tree-kill on quit.

## Reimplemented (continued)

- [x] **Office skill quality** — md2pptx design system (5 themes, 8 slide
  families), md2docx cover/heading/table/footer styling, make_xlsx real
  tables + totals + charts; UTF-8-safe readers.
- [x] **Viewport resize fix** — layout classes re-sync when the window is
  resized across breakpoints.
- [x] **Todo checklist tool** — `todo` tool + web checklist card.
- [x] **Revert coverage for skills/memories** — `save_skill`/`remember`
  writes are checkpointed and undone by chat revert.
- [x] **Settings** — global rules, UI scale (80–150%), optional model
  (blank = first from `/v1/models`).
- [x] **Diff cards for edit_file** — already present in the web client.
- [x] **Terminal** — xterm.js drawer tab over a websocket PTY endpoint
  (ConPTY/pywinpty on Windows, openpty+subprocess elsewhere), same
  local-only origin rules as the HTTP API.
- [x] **CI job timeouts** — every workflow job is bounded.

## Next

1. **Skill-loop guardrails, minimally** — port ONLY the improved
   unknown-tool error message if hallucinated tool names reappear. Do NOT
   port tool_policy or the prompt rewrite — they were the behavior
   regression.
2. **Packaging refresh** — electron-builder with the PyInstaller sidecar in
   `resources/sidecar`; retire pywebview. Do this with the next release.

## Explicitly NOT coming back (v2 regressions)

- `tool_policy.py` per-turn tool scoping and the v2 system-prompt rewrite
  (models hallucinated tools, lost capabilities mid-conversation).
- Turn-scoped skill activation with prompt-only instruction delivery
  (caused skill-reload loops).
- The post-error "save what you learned" nudge (junk-skill spam).
- The PySide6 native client.

Each item ships alone: implement → full pytest → drive the real UI →
only then move to the next.
