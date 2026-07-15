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

## Next, in order (one PR-sized change each)

1. **Todo checklist tool** — `todo` tool + web UI checklist card
   (v2-archive: `tools/__init__.py`, tool card rendering).
2. **Revert coverage for skills/memories** — checkpoint `save_skill` /
   `remember` writes so chat revert undoes them (v2-archive has the
   implementation + test).
3. **Skill-loop guardrails, minimally** — keep v1.1.1's inline skill bodies
   (already the behavior here); port ONLY the improved unknown-tool error
   message. Do NOT port tool_policy or the prompt rewrite — they are the
   suspected behavior regression.
4. **Settings: global rules + text size + optional model** — server keys
   exist in v2-archive; add fields to the web settings dialog.
5. **Diff cards for edit_file** — colored diff rendering in the web tool
   card (the web UI may already show raw args; add the diff view).
6. **Terminal** — xterm.js panel + a websocket PTY endpoint on the server
   (ConPTY via pywinpty on Windows, `pty.openpty` + `subprocess` elsewhere —
   never `pty.fork` in-process; see v2-archive `widgets.py` backends).
7. **CI job timeouts** — port `timeout-minutes` to the build workflow.
8. **Packaging refresh** — electron-builder with the PyInstaller sidecar in
   `resources/sidecar`; retire pywebview.

## Explicitly NOT coming back (v2 regressions)

- `tool_policy.py` per-turn tool scoping and the v2 system-prompt rewrite
  (models hallucinated tools, lost capabilities mid-conversation).
- Turn-scoped skill activation with prompt-only instruction delivery
  (caused skill-reload loops).
- The post-error "save what you learned" nudge (junk-skill spam).
- The PySide6 native client.

Each item ships alone: implement → full pytest → drive the real UI →
only then move to the next.
