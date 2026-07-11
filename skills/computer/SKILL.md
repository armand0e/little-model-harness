---
name: computer
description: Control the computer — open apps, manage windows, type, click, take screenshots
category: office
hint: control apps, windows, keyboard, mouse, screenshots
---
Control the desktop with the helper script via run. General form:
`run("python \"{dir}\scripts\computer.py\" <command> [args]")`

Commands:
- `open <app or path>` — open an app, file, or URL (e.g. `open notepad`, `open https://site.com`, `open report.docx`)
- `windows` — list open window titles
- `focus "<partial title>"` — bring a window to the front
- `type "<text>"` — type text into the focused window (use \n for Enter)
- `press <keys>` — press a key combo, e.g. `press ctrl+s`, `press enter`, `press alt+f4`
- `click <x> <y>` / `doubleclick <x> <y>` / `rightclick <x> <y>`
- `scroll <amount>` — positive = up, negative = down
- `screenshot [path]` — save a screenshot (default: workspace/screenshot.png) and report the screen size
- `checkperms` — macOS only: report whether Accessibility/Screen Recording access is granted
- `wait <seconds>` — pause (use after opening apps so they finish loading)

Rules:
- You cannot see the screen. Prefer keyboard-driven flows (open, focus, type, press) over clicking at coordinates. Only click coordinates the user gave you.
- ALWAYS `focus` a window before typing into it, and `wait 2` after `open`.
- To save in most apps: `press ctrl+s`, then `wait 1`, then `type "filename\n"`.
- macOS: `ctrl+`/`alt+` combos are auto-translated to `command`/`option`. The FIRST desktop-control action asks the user to grant permissions (Accessibility for typing/clicking, Screen Recording for screenshots, Automation for window listing) — if a command reports a missing permission, run `checkperms`, tell the user exactly what to enable in System Settings > Privacy & Security, and wait for them to confirm before retrying.
- Prefer file tools and skill scripts over UI automation when both can do the job (e.g. create a .docx with the documents skill, THEN `open` it for the user).
- Tell the user what you did to their screen.
