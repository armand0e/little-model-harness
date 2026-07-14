---
name: computer
description: Control the computer — open apps, manage windows, type, click, take screenshots
---
Use the first-class `computer` tool. Packaged builds attach a pinned native MCP
backend for the running OS: Windows UI Automation, macOS Accessibility, or
Linux AT-SPI. It returns semantic element IDs and updated screenshots, which is
far more reliable than guessing coordinates.

Efficient workflow:
1. Use `computer(action="open_app", app="...")` when the app is not running,
   then `list_apps` to discover its exact runtime name if needed.
2. `computer(action="get_state", app="...")` once before the first action.
   Read the compact accessibility tree and inspect the attached screenshot.
   After `open_app` or a successful state call, `app` may be omitted on later
   actions because the harness remembers the active app.
3. For named targets, call `computer(action="find", query="Gmail")`, or pass
   `query` directly to `click`, `focus`, `set_value`, or `scroll`. This is safer
   than scanning a long tree or guessing an ID from screenshot position.
4. Prefer `set_value`, `click`, and `scroll` with the returned `element` ID.
   Use `focus` on an editable control before `type_text` or keyboard shortcuts.
   For browser navigation: focus the numeric address-bar element, set its value,
   then press `Return` and verify the resulting title/page state.
5. Action results contain updated state/screenshot evidence. Use it directly;
   do not call `get_state` again unless the UI is ambiguous or changed outside
   the tool.
6. Use x/y coordinates only for canvas, games, or inaccessible custom widgets,
   and only after inspecting a current screenshot.
7. Element IDs are numeric. Never invent an `AX:` label or use visible text as
   an element ID.

Actions: `open_app`, `list_apps`, `get_state`, `find`, `focus`, `click`, `set_value`, `type_text`,
`press_key`, `scroll`, `drag`, `secondary_action`. The non-list actions require
`app`; semantic actions generally take `element`. `press_key` examples include
`ctrl+s`, `Return`, `Tab`, and arrow keys.

Rules:
- Never claim an action worked without checking the returned state or image.
- Prefer file tools and deterministic skill scripts when direct file editing is
  possible; use desktop control for interactions that genuinely require an app.
- macOS requires Accessibility and Screen Recording grants. Linux needs a
  signed-in graphical session with AT-SPI/D-Bus. Windows needs the signed-in
  interactive desktop session. Report permission/readiness errors exactly.
- Tell the user what you changed on their screen.
- If state capture fails twice, stop and report the first error. Never change
  `OPEN_COMPUTER_USE_*` variables or replace computer control with shell GUI
  automation; the harness owns backend configuration and retry limits.

Legacy source fallback only: if the native backend is unavailable, the old
helper remains at `python "{dir}\scripts\computer.py" <command> [args]` for
basic open/focus/type/press/click/screenshot operations. It is not the preferred
path because it has no semantic element tree and starts a process per action.
