# Little Model Harness

An agentic harness engineered for **small local LLMs** (32k context) and
**everyday office work** — not just coding. It turns any OpenAI-compatible
local model (LM Studio, llama.cpp, Ollama) into an assistant that can write
Word documents, build Excel spreadsheets, make PowerPoint decks, research the
web, control the computer, and work on code.

## Quick start

```powershell
pip install -r requirements.txt

# terminal UI
python -m harness.tui

# web UI  →  http://localhost:8321
python -m harness.server
```

The web app is a full local chat client: multiple conversations with
history that survives restarts, live streaming with a
collapsible thought process, expandable tool cards, a stop button (Esc),
markdown + code blocks with copy, a workspace-files drawer with one-click
downloads, a skills browser, settings (temperature, max output tokens),
search across chats, light/dark/system theming, and Ctrl+K for a new chat.

**Artifacts**: a split-view panel (▣, draggable divider) that previews what
the agent makes — Word docs, Excel sheets (with formula tooltips),
PowerPoint decks, PDFs, markdown, CSV, images, and HTML — rendered
server-side to clean HTML (`harness/preview.py`). HTML the model writes in
chat previews **live while it streams**; files created during a turn pop
open automatically; any workspace file can be opened from the Files drawer.
Assistant messages have copy / regenerate / edit-prompt actions.

**Web** is free and keyless: a `web_search` core tool (DuckDuckGo HTML
endpoints, parsed server-side) plus `fetch`, which falls back to the
keyless r.jina.ai reader for JS-heavy pages.

**Attachments**: paste, drag-drop, or ＋-attach files/images into the
composer. They're saved into the workspace and the message carries only
their names (~15 tokens) — the model reads them with tools when needed,
which is the context-frugal way for a small model.

**Settings** (persisted in the data dir's `user_settings.json`):
temperature, max output tokens (up to 16k), and the model endpoint — base
URL, model ID, API key, context window. The Settings workspace field sets
the **default folder new chats inherit**.

**Per-chat workspaces**: every chat has its own working folder — the 📁
chip above the message box shows it; click it and the OS-native folder
picker points *that chat* at any directory. The sidebar groups chats by
their workspace folder (projects), the Files drawer shows the active
chat's folder live, and file management (new folder, rename, delete —
hover a row) works right in the drawer.

**Data dir**: everything the harness writes lives per-user —
`%LOCALAPPDATA%\LittleHarness` on Windows,
`~/.local/share/LittleHarness` on Linux, `~/Library/Application
Support/LittleHarness` on macOS: sessions, settings, memory, learned
skills (`save_skill` writes here, shadowing bundled skills by name), the
browser profile, and the default workspace. Data from older versions that
lived in the project root is migrated automatically on first start.

**Small-context resilience** — the motto in practice: the harness asks the
model server for its real `n_ctx` and clamps its window to it (load a model
at 4k and everything adapts); each response's `max_tokens` is clamped to
the space actually left, so a 16k max output never causes "exceeds context"
errors; per-tool-result caps scale with the window.

**Long agentic turns**: the step limit is 100 (a runaway guard, not a
budget). The real constraint is context: compaction fires when the
conversation reaches `window − 16384` (16k of generation headroom,
floored at half the window) — **including mid-turn**. Fading and
compaction both work inside a single long turn (one user message, dozens
of tool rounds), so a heavy debugging session compacts and continues
instead of dying.

**Feedback from reality, automatically**: every `write_file`/`edit_file`
comes back with a verification report in the same tool result — `.html`
files are loaded in a headless browser and console errors / uncaught
exceptions / failed resource loads are reported (the way a user would see
them), `.py` gets a syntax check, `.js` gets `node --check`. The model
fixes its own bugs before claiming success, at zero extra steps.

**Revert**: hover any of your messages and hit ⤺ to rewind the chat to
that point AND restore every file the assistant wrote or edited after it
(before-images are checkpointed automatically). Regenerate/edit-prompt use
the same machinery, so redoing a turn starts from a clean slate.

**The learning loop** (Hermes-style): the agent can `remember` durable
facts (injected into every future system prompt; view them in the Memory
drawer tab), `save_skill` to persist hard-won know-how into the skills
index, and `history_search` past sessions for how something was solved
before. After a turn that fought through several tool errors, the harness
nudges the model to bank what it learned. Project context files
(`AGENTS.md`/`CLAUDE.md` in the workspace) are injected automatically.

**Subagents**: the `subtask` tool runs an isolated helper agent with a
fresh context on a self-contained task — the parent gets only the final
summary, keeping long digressions out of its window.

**UI**: live workspace file tree (recently-changed files pulse), a console
strip under HTML artifact previews showing the page's JS errors as they
happen, and real red/green diffs on edit_file tool cards. Plus the
desktop-app comforts: **pin chats**, sidebar search that looks **inside
conversations** (with snippets), **export any chat to Markdown**, desktop
**notifications when a slow turn finishes** while you're in another tab,
select any text in a chat to **quote it in your reply**, per-chat draft
persistence, a scroll-to-latest button, Alt+↑/↓ to switch chats, and
Ctrl+/ for the shortcut list.

**Vision**: if the loaded model is multimodal (probed automatically with a
1-pixel image), `read_file` on a .png/.jpg/etc. shows the model the actual
image (downscaled to ≤1024px), and on a .pdf renders pages to images
(`start_line` = first page, `max_lines` = page count). Old attached images
are dropped first when the context gets tight. Text-only models get a
polite "can't view images" result instead of an error.

Point it at your model with env vars if the defaults don't match:
`LMH_BASE_URL` (default `http://localhost:1234/v1`), `LMH_MODEL` (default
`llm`), `LMH_WORKSPACE` (default-workspace override), `LMH_DATA_DIR`
(where sessions/settings/memory live, default is the per-user data dir).
Or create a `harness.toml` in the project root with any `Config` field
(see `harness/config.py`).

## Why small models need a different harness

Frontier harnesses assume 200k contexts and strong instruction-following.
This harness assumes neither, and is built around a strict token budget:

| Layer | Mechanism | Cost |
|---|---|---|
| System prompt | Short, imperative, ~300 tokens | always |
| Tools | 8 core tools with minimal schemas (~700 tokens) | always |
| Skills | Category-grouped index of short hints in prompt; full instructions injected only when the model calls `skill(name)` | on demand |
| Tool results | Hard-capped at insertion (6k chars, head+tail) | per call |
| Fading | Tool results older than 2 user turns collapse to a stub | automatic |
| Compaction | Model summarizes the older half of the chat when the estimated prompt passes 20k tokens | automatic |

Token estimates are continuously calibrated against the exact
`usage.prompt_tokens` the server reports, so the meter stays honest.
A typical office task (skill load → create file → verify) completes in
under 3k tokens.

The harness also survives small-model failure modes: tool calls whose JSON
arguments get cut off by the output limit are discarded and explained back
to the model (instead of poisoning the history and making llama.cpp 500 on
every later request), and the loop bails out with advice after repeated
cut-off calls.

## Skills

Skills live in `skills/<name>/SKILL.md`. Frontmatter: `name:`,
`description:` (full trigger text, shown to humans and used as fallback),
`category:` (office / software / writing / reasoning / math / science /
creative), and `hint:` (≤10 words — this is what goes in the always-loaded
index, so keep it tight). The office skills pair instructions with
**deterministic helper scripts**, so the model writes simple Markdown/JSON
and the script does the fiddly library work — far more reliable for small
models than generating `python-docx` code:

- **documents** — Markdown → styled .docx (`md2docx.py`); readers for .docx and .pdf
- **spreadsheets** — JSON spec → .xlsx with live formulas, styled headers, auto-width (`make_xlsx.py`); .xlsx reader
- **presentations** — Markdown outline → .pptx with title/bullet/statement slides and speaker notes (`md2pptx.py`); .pptx reader
- **computer** — open apps, focus windows, type, press hotkeys, click, screenshot (`computer.py`, keyboard-first because the model can't see the screen)
- **coding** — orient → plan → smallest edit → verify workflow rules
- **research** — fetch-based web research with source citing

**Add your own skill** by creating `skills/mytask/SKILL.md`. Use `{dir}` in
the body to reference helper scripts in your skill folder. It appears in the
index automatically on next start.

## Core tools

`read_file, write_file, edit_file, list_dir, search, run (PowerShell),
fetch (web page → text), skill` — everything else goes through `run` +
skill scripts, which keeps the always-loaded schema surface tiny.

## Layout

```
harness/          core package
  agent.py        the loop: prompt → tool calls → results → repeat
  context.py      budget enforcement: capping, fading, compaction
  skills.py       skill index + on-demand loading
  tokens.py       estimation + calibration against real usage
  llm.py          OpenAI-compatible client w/ streaming + tool-call assembly
  tools/          core tool implementations
  tui.py          terminal UI      (python -m harness.tui)
  server.py       web UI backend   (python -m harness.server [port])
web/index.html    single-file web frontend (SSE streaming, no build step)
skills/           bundled skill packs (SKILL.md + scripts/)
packaging/        PyInstaller spec + build scripts (.exe / Linux binary)
test_live.py      live smoke test:   python test_live.py "prompt"
test_context.py   fading/compaction synthetic test

<data dir>/       %LOCALAPPDATA%\LittleHarness (or XDG equivalent)
  sessions/       chat history
  skills/         skills the agent saved with save_skill
  workspace/      fallback default workspace
  memory.md       remember-tool facts
  user_settings.json, browser-profile/
```

## Packaging as an app

Little Harness ships as a real desktop application — a native window
(WebView2 on Windows, Qt on Linux) around the local server, launched from
an icon like any other app. No terminal, no browser tab.

```powershell
# Windows — builds dist\LittleHarness\ and dist\LittleHarness-Setup.exe
# (Inno Setup; winget install JRSoftware.InnoSetup). The installer puts the
# app in %LOCALAPPDATA%\Programs\LittleHarness with a Start Menu entry,
# optional desktop icon, and an uninstaller — no admin rights needed.
powershell -File packaginguild_windows.ps1
```

```bash
# Linux — builds dist/LittleHarness-x86_64.AppImage (works in WSL too).
# Download, chmod +x, double-click.
bash packaging/build_appimage.sh

# macOS — builds "dist/Little Harness.app" + dist/LittleHarness.dmg.
# Must run on a Mac; ad-hoc signed, so first launch is right-click > Open.
bash packaging/build_macos.sh
```

No Mac (or Linux) machine? `.github/workflows/build.yml` builds all
platforms on GitHub Actions: run it from the Actions tab, or push a tag
like `v1.0.0` to get a release with the Windows installer, Linux
AppImage, and Intel + Apple Silicon DMGs attached.

The bundle contains the server, web UI, bundled skills, and every library
the skill helper scripts need. Machines without Python still run skill
scripts: inside the app, `python` is aliased to the bundled interpreter
(`LittleHarnessCLI --runpy`). Web tools use your installed Chrome/Edge;
all writable data goes to the per-user data dir, so the install folder
stays read-only. `LittleHarness --server-only` (or `LMH_NO_WINDOW=1`)
runs it headless on http://127.0.0.1:8321 for the classic browser
workflow.

## Safety notes

The `run` tool executes PowerShell (bash on macOS/Linux) and the computer
skill controls your mouse/keyboard — the agent has the same power as your
user account. Watch what it does (both UIs show every command before its
output), and don't point it at untrusted instructions. pyautogui's
failsafe is on: slam the mouse into the top-left corner to abort desktop
automation.

On macOS, desktop automation is gated by the system: the first
type/click/screenshot/window action pops permission prompts, and the app
must be enabled under System Settings > Privacy & Security >
**Accessibility** (keyboard/mouse), **Screen Recording** (screenshots),
and **Automation** (window control via System Events). The computer
skill detects missing grants and tells the model to walk the user
through enabling them (`checkperms` reports the current state).
