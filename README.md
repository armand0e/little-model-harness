# Little Model Harness

An agentic harness engineered for **small local LLMs** (32k context) and
**everyday office work** — not just coding. It turns any OpenAI-compatible
local model (LM Studio, llama.cpp, Ollama) into an assistant that can write
Word documents, build Excel spreadsheets, make PowerPoint decks, research the
web, control the computer, and work on code.

## Quick start

```powershell
# Python 3.11 or newer
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
downloads, a skills browser, settings (temperature, model endpoint, and context window),
search across chats, light/dark/system theming, and Ctrl+K for a new chat.

Pasted and uploaded images appear directly in the user message and open into a
full-size lightbox. Video and audio attachments play inline; documents and
other supported files open in the artifact viewer. Attachment metadata is
saved with the chat, while file contents remain in that chat's workspace.

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
composer. They're saved into the workspace, rendered as previewable chips in
the composer, and shown as image thumbnails or openable file cards in chat.
The model-facing message carries compact workspace paths and reads file content
with tools when needed, which keeps the prompt small.

**Settings** (persisted in the data dir's `user_settings.json`):
temperature, maximum output tokens per model call, and the model endpoint —
base URL, model ID, API key, and context window. Every output request is capped
by both the configured maximum and the space remaining in the active context.
The Settings workspace field sets
the **default folder new chats inherit**.

**Model selector**: the model pill in the top bar is populated from the
configured OpenAI-compatible `GET /v1/models` endpoint. Changing it updates
all sessions, reconfigures existing clients, and re-detects that model's
reported context window. A model ID can still be entered manually for servers
that do not implement model listing.

**Chat / Code modes**: the prominent top-bar switch changes between two
separate conversation histories. Chat mode is a deliberately simple text
conversation with no tool schemas, workspace controls, attachments, or
artifact UI. Code mode exposes the full file, shell, web, skill, computer,
and MCP environment. Switching surfaces restores that mode's last-opened
conversation; it never silently converts an existing conversation.

All confirmations, errors, destructive actions, and rename/create inputs use
accessible in-app dialogs. The UI never relies on blocking browser
`alert`, `confirm`, or `prompt` popups.

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
conversation reaches `window − 8192` (at least 8k of generation headroom;
larger output caps reserve `max_output_tokens + 512`) — **including mid-turn**.
It targets two-thirds of that
ceiling, rechecks the budget, and can compact again if one pass was not enough.
Fading preserves user text while removing old images and tool payloads. If the
model summarizer is unavailable, a deterministic handoff retains the goal and
recent factual trace instead of silently dropping history.

**Background queue**: different chats can submit work while the local model is
busy. Jobs show queued/running state and position in the sidebar, stream when
their turn begins, and can be cancelled independently. Queue state is written
atomically to `jobs.json`; after an unclean restart, work that had not started
is resumed. A job that was already running is recorded as interrupted rather
than replayed, because its tool actions may already have changed files.

While a chat is working, its composer remains available. New text can either
be **queued** as that chat's next persisted turn or used to **steer** the
current turn. Steering is applied at the next safe model boundary—after a
model response or after all required tool results—so it cannot break tool-call
ordering. Queued messages appear above the composer, can be removed, or can be
promoted to a steer while the turn is still active.

**Feedback from reality, automatically**: every `write_file`/`edit_file`
comes back with a verification report in the same tool result — `.html`
files are rendered in a real headless Chromium browser at desktop and mobile
sizes. Screenshots are shown in the tool card and attached to vision-capable
models, alongside horizontal-overflow, broken-image, console, uncaught-error,
and failed-resource diagnostics. `.py` gets a syntax check and `.js` gets
`node --check`.

The explicit `visual_check` tool captures desktop/tablet/mobile views of an
HTML file or localhost app. It can click a CSS selector, scroll an element
into view, label the resulting state, wait for animation/data settling, and
optionally capture the full page. The system and coding/UI skills require the
model to inspect those images, exercise important menus/modals/error/empty
states, fix visible issues, and re-run the check. A clean console alone is
never described as visual verification. Generated QA screenshots live under
the workspace's hidden `.lmh/visual-qa` directory and are rotated automatically.

**Revert**: hover any of your messages and hit ⤺ to rewind the chat to
that point and restore files changed through `write_file` / `edit_file`
(before-images up to 500 KB are checkpointed automatically, including changes
made by a subtask). Arbitrary filesystem changes made through shell commands
cannot be checkpointed. Regenerate/edit-prompt use
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
| Tools | 14 core tools with compact schemas (~1,500 tokens) | always |
| Skills | Deterministic task routing injects the most relevant full instructions; the model can load additional skills with `skill(name)` | per Code turn |
| Tool results | Hard-capped at insertion (6k chars, head+tail) | per call |
| Fading | Tool results older than 2 user turns collapse to a stub | automatic |
| Compaction | Model summarizes older context at `window - reserve` (16,384 tokens by default) | automatic |

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

At the start of every Code turn, the harness refreshes the catalog and
deterministically selects up to three relevant skills from the request. Each
selection is visible as a completed skill card in the conversation. This does
not depend on a small model remembering to call a tool; it may still call
`skill(name)` when it needs a specialist skill the router did not select.

- **documents** — Markdown → styled .docx (`md2docx.py`); readers for .docx and .pdf
- **spreadsheets** — JSON spec → .xlsx with live formulas, styled headers, auto-width (`make_xlsx.py`); .xlsx reader
- **presentations** — Markdown outline → .pptx with title/bullet/statement slides and speaker notes (`md2pptx.py`); .pptx reader
- **computer** — semantic app state, accessibility element IDs, keyboard/mouse,
  and model-visible screenshots through the bundled native OS backend
- **coding** — orient → plan → smallest edit → verify workflow rules
- **research** — fetch-based web research with source citing

**Add your own skill** by creating `skills/mytask/SKILL.md`. Use `{dir}` in
the body to reference helper scripts in your skill folder. It appears in the
index automatically on next start.

## Core tools

`read_file`, `write_file`, `edit_file`, `visual_check`, `list_dir`, `search`, `run`
(PowerShell/bash), `web_search`, `fetch`, `skill`, `save_skill`, `remember`,
`history_search`, `subtask`, and `computer`. The single compact `computer`
schema fronts nine native MCP operations; specialized document, spreadsheet,
presentation, and domain workflows still go through `run` plus skill scripts.

### MCP servers

Code mode is an MCP client for persistent local stdio servers. Configure the
same command/args shape used by Claude Desktop in Settings:

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Work"],
    "env": {},
    "enabled": true
  }
}
```

The packaged app automatically attaches
[`@qwen-code/open-computer-use` 0.2.3](https://github.com/QwenLM/open-computer-use)
under its MIT license. The build verifies the npm artifact's pinned SHA-256
and bundles only the current OS/architecture runtime: Windows UI Automation,
macOS Accessibility, or Linux AT-SPI. It is shown separately from editable
third-party MCP JSON in Settings. Set `LMH_DISABLE_COMPUTER_USE=1` to disable
it; source runs may point `LMH_COMPUTER_USE_BIN` at a trusted installation.

Servers connect once and remain alive; discovered tools are namespaced as
`mcp_<server>_<tool>` so they cannot replace a core harness tool. Invalid or
offline servers are isolated from the others and reported in Settings. Up to
20 servers and 200 MCP tools are accepted. This initial client supports tools
over local stdio; remote OAuth/Streamable HTTP, MCP resources, and MCP prompts
are not yet exposed.

## Layout

```
harness/          core package
  agent.py        the loop: prompt → tool calls → results → repeat
  context.py      budget enforcement: capping, fading, compaction
  skills.py       skill index + on-demand loading
  tokens.py       estimation + calibration against real usage
  llm.py          OpenAI-compatible client w/ streaming + tool-call assembly
  mcp_client.py   persistent local stdio MCP connections + tool discovery
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
  user_settings.json, jobs.json, browser-profile/
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
powershell -File packaging\build_windows.ps1
```

```bash
# Linux — builds dist/LittleHarness-x86_64.AppImage (works in WSL too).
# Download, chmod +x, double-click.
bash packaging/build_appimage.sh

# macOS — builds "dist/Little Harness.app" + dist/LittleHarness.dmg.
# Must run on a Mac; ad-hoc signed, so first launch is right-click > Open.
bash packaging/build_macos.sh
```

No Mac (or Linux) machine? `.github/workflows/build.yml` builds and
smoke-tests every platform on its native GitHub Actions runner. Every push to
`main` produces downloadable workflow artifacts. Pushing an `X.Y.Z` tag such
as `v1.0.0` also creates or updates the GitHub release with the Windows x64
installer, Linux x86_64 AppImage, Intel DMG, Apple Silicon DMG, and a
`SHA256SUMS.txt` manifest. The macOS jobs use explicit ARM64 and Intel runner
labels so a future `macos-latest` migration cannot silently change the target.

The bundle contains the server, web UI, bundled skills, the pinned native
computer-use MCP (with its license/source manifest), and every library
the skill helper scripts need. Machines without Python still run skill
scripts: inside the app, `python` is aliased to the bundled interpreter
(`LittleHarnessCLI --runpy`). Web tools use your installed Chrome/Edge;
all writable data goes to the per-user data dir, so the install folder
stays read-only. `LittleHarness --server-only` (or `LMH_NO_WINDOW=1`)
runs it headless on http://127.0.0.1:8321 for the classic browser
workflow.

## Safety notes

The `run` tool executes PowerShell (bash on macOS/Linux) and the `computer`
tool controls desktop apps — the agent has the same power as your
user account. Watch what it does (both UIs show every command before its
output), and review consequential actions. Uploaded files, fetched pages,
search results, and tool output are treated as untrusted data in the system
prompt, but a local model can still make mistakes. HTML artifacts run in a
sandboxed, opaque-origin frame; workspace file APIs are loopback-only and
path-confined. A remote model endpoint receives the prompts, memory, project
notes, and tool context sent to the model, and the Settings screen warns when
the configured endpoint is not local. Stop generation immediately if an
action heads in the wrong direction. The legacy pyautogui fallback also
supports its top-left-corner failsafe.

MCP server commands also execute locally with your user account. Install only
servers you trust, review their command/arguments and requested environment
variables, and restrict filesystem-server roots to the folders they actually
need.

On macOS, desktop automation is gated by the system: the first native state,
screenshot, or action request may prompt, and the app must be enabled under
System Settings > Privacy & Security > **Accessibility** (semantic UI and
input) and **Screen Recording** (screenshots). On Linux it needs a signed-in
graphical session with AT-SPI2 and the session D-Bus available. On Windows it
must run in the signed-in interactive desktop session rather than as a
service. Readiness errors are returned directly to the model instead of
encouraging coordinate guessing.
