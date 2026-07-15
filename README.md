# Little Harness

Little Harness turns a small local OpenAI-compatible model into a practical
desktop agent. It can chat, work in a repository, create office documents,
inspect the web, operate public websites, use a terminal, control desktop
applications, call MCP servers, and verify the artifacts it creates.

The primary application is a real cross-platform native desktop client built
with PySide6/Qt. The UI calls the Python agent and job system in-process; it
does not put a browser shell around a localhost web app.

## Run from source

Python 3.11 or newer is required.

```powershell
python -m pip install -r requirements.txt
python run_app.py
```

Optional compatibility and diagnostic entry points:

```powershell
# terminal client
python -m harness.tui

# legacy browser client at http://127.0.0.1:8321
python -m harness.server

# packaged/headless API mode
python run_app.py --server-only
```

By default the model endpoint is `http://localhost:1234/v1` and the model ID
is `llm`. Change them in Settings or with `LMH_BASE_URL`, `LMH_MODEL`, and
`LMH_API_KEY`.

## Native desktop experience

The custom title bar, sidebar, conversation timeline, composer, dialogs,
menus, selectors, file browser, previews, terminal, and browser inspector are
native Qt widgets. Icons are bundled SVGs, not emoji or platform-dependent
font glyphs.

### Separate Code, Chat, and Deep research spaces

Code tasks, simple chats, and deep research are selected in the sidebar. Each
mode owns its own history and search results:

- **Code** enables workspaces, attachments, files, artifacts, skills,
  terminal, managed browser, shell/file/web/computer tools, and MCP.
- **Chat** is a lightweight text conversation without the coding/tool
  environment.
- **Deep research** turns one request into a cited multi-source report (see
  below).

There is no duplicate mode switch in the top toolbar. Switching the sidebar
section changes the visible history and starts new conversations in that
mode; existing conversations are never silently converted.

### Deep research mode

Deep research runs a structured multi-phase pipeline instead of a free-form
tool loop, so it stays dependable on small local models:

1. **Scope** — one model call decides whether to ask up to three clarifying
   questions (first turn only), answer a quick follow-up from the previous
   report, or produce a research brief with sub-questions and initial search
   queries.
2. **Research rounds** — each round searches the web, has the model triage
   which results to read, fetches the pages, and extracts source-grounded
   notes. After a round, a reflection step either declares coverage complete
   or issues new queries aimed at the remaining gaps.
3. **Synthesis** — the model streams a markdown report with an executive
   summary, thematic sections, tables where useful, and inline `[n]`
   citations. A Sources section is appended deterministically from the notes
   actually cited, and the report is saved to the conversation's workspace as
   `research-report-<timestamp>.md`.

Every model call in the pipeline is standalone and budget-bounded, so the
mode works from 8k-context models upward and scales the number of rounds,
queries, and sources with the window. Stop and mid-turn steering work the
same as other modes; steering text is folded into the research brief at the
next phase boundary. `research_max_rounds` and `research_max_sources` in
`harness.toml` cap the effort.

### Models and settings

The model pill is populated from the configured OpenAI-compatible
`GET /v1/models` endpoint. Models that report `n_ctx` display it alongside the
ID. A manual model ID still works with servers that do not implement model
listing.

Settings are persisted before live reconfiguration starts. Saving happens in
the background, the dialog stays open, and model/MCP health is updated in the
dialog instead of freezing or disappearing. Validation and connectivity
errors remain visible and do not discard the entered values.

### Generation control and follow-ups

Generation runs in a persisted background queue. The stop button and Escape
request cancellation immediately, including closing an active model stream.
Queued jobs can be cancelled before they start.

While a task is active, another message can be:

- **Queued** as the next complete turn for that conversation.
- **Steered** into the current turn at the next safe model boundary.

Pending messages appear above the composer and can be removed or promoted to
a steer. A crash-recovered queued job resumes; a job that had already started
is marked interrupted so destructive tool actions are not replayed.

### Attachments and artifacts

Paste an image, drag files into the composer, or use the attach button. Images
appear as thumbnails in the user message and open in a full-size native
preview. Other attachments appear as openable file cards. Attachment metadata
stays with the conversation while contents remain in its workspace.

The Preview panel handles images, PDF pages, text/source, Word text and
tables, spreadsheet cells, and slide text. The Files panel supports refresh,
new folders, rename, delete, and open-in-preview. The system application is
still available for formats that need full editing fidelity.

### Built-in terminal and managed browser

Code mode includes a real terminal panel rooted at the current workspace: a
ConPTY-backed PowerShell on Windows and a pty-backed shell on macOS/Linux,
emulated with pyte. Type directly into it — tab completion, arrow history,
Ctrl+C/Ctrl+R, and interactive redraws behave like a normal terminal, with
Ctrl+Shift+C/V for copy and paste, scrollback, clear, and restart. If the PTY
backend is unavailable, a simpler pipe-based prompt is used instead.

The managed Browser panel and the model-facing `browser` tool share a
persistent Chromium profile. The panel is directly interactive: click,
scroll, and type on the live page image, or use the address bar. Browser
actions return:

- the current URL and title;
- compact visible page text;
- fresh semantic element references such as `e1` and `e2`;
- a screenshot after every action.

The model must use references from the latest state and verify the updated
text, URL, and screenshot after clicking, typing, selecting, scrolling, or
pressing a key. Public interactive sites use `browser`; read-only research
uses `web_search`/`fetch`; local HTML and localhost visual QA use
`visual_check`; desktop application chrome uses `computer`.

## Agent design for small local models

### Context engineering

The harness asks the model server for its real context window and clamps the
configured window to it. Output tokens are capped by both the user setting and
the remaining prompt budget. Tool-result limits scale with the window.

Each turn receives an automatic compact, lean, balanced, or full capability
profile based on the real window and the task. Only relevant tool schemas are
sent to the model, the selection remains stable for the turn, and configured
MCP catalogs stay behind progressive `mcp` search. The context tooltip shows
the active profile, system/tool/conversation token split, and exposed tools.

Compaction reserves generation headroom and can run during a long tool loop,
not only between user turns. It preserves the goal, recent decisions, file
state, errors, and unresolved work. If model summarization is unavailable, a
deterministic handoff is used instead of dropping history. Old image and tool
payloads fade before user intent does, and token estimates are calibrated
against usage reported by the model server.

The step limit is a runaway guard rather than a planning budget. A healthy
turn stops because it completed, the user cancelled it, context could not be
made safe, or repeated failures triggered an explicit error—not because the UI
silently lost a worker.

### Skills

Skills live in `skills/<name>/SKILL.md` and use standard frontmatter:

```yaml
---
name: browser-control
description: When and why the model should use this skill.
---
```

At the beginning of every Code turn, deterministic routing preloads one to
three strongly relevant skills according to context capacity. Selection is visible as a completed skill
card, so it does not depend on a small model remembering to call `skill`.
The prompt contains only a compact catalog; the model can search it by
capability and activate another skill later. Active skill text has a
window-aware budget and is never duplicated into the tool result. The catalog refreshes between turns,
and `save_skill` writes learned skills to the per-user data directory so the
installed application remains read-only.

Bundled capabilities include document, spreadsheet, presentation, coding,
debugging, UI/UX, visual verification, research, browser-control,
terminal-workflows, computer automation, reasoning, math, science, game, and
3D workflows.

### Visual verification

Writing or editing an HTML file automatically returns visual diagnostics from
a real Chromium render. The `visual_check` tool captures desktop, tablet, and
mobile views, plus important interaction states when a selector and state label
are supplied. It reports console errors, uncaught exceptions, failed resources,
broken images, and horizontal overflow.

UI and coding skills require the model to inspect the screenshots, exercise
menus/modals/error/empty states where relevant, fix visible problems, and run
the check again. A clean console is not treated as visual verification.
Screenshots are stored under the workspace's `.lmh/visual-qa` directory and
rotated automatically.

### Tools

The Code environment can expose the following capabilities; the per-turn
profile sends only the subset relevant to the request:

- `read_file`, `write_file`, `edit_file`, `list_dir`, and `search`;
- `run` for bounded PowerShell/bash commands;
- `visual_check` for local UI rendering and screenshots;
- `web_search` and `fetch` for read-only web research;
- `browser` for interactive public websites;
- `computer` for semantic OS accessibility and input;
- `mcp` for namespaced third-party MCP tools;
- `skill`, `save_skill`, `remember`, `history_search`, and `subtask`.

Direct MCP schemas are not dumped into every prompt; `mcp` searches and calls
the configured catalog on demand. Tool calls, results, errors, and screenshots are shown in the conversation.
Stopping a turn propagates to the model stream and active subtask. Shell and
browser, web, computer, visual-check, and MCP operations observe cancellation
rather than being allowed to hold a stopped job open. Truncated text responses
continue automatically, while repeated identical failed calls trigger recovery
guidance and then stop before exhausting the step limit.

### MCP and computer control

Configure persistent stdio MCP servers in Settings with the same command/args
shape used by other desktop clients:

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

Server tools are namespaced so they cannot replace core tools. Invalid or
offline servers are isolated and reported through Settings. The client limits
server and tool counts and currently supports local stdio transport.

Release packages also include the pinned MIT-licensed
`@qwen-code/open-computer-use` runtime for the current OS/architecture:

- Windows UI Automation;
- macOS Accessibility;
- Linux AT-SPI.

The `computer` facade requires a fresh semantic state before interaction and
rejects guessed or stale element IDs. It returns a new state and screenshot
after actions. Set `LMH_DISABLE_COMPUTER_USE=1` to disable it or
`LMH_COMPUTER_USE_BIN` to use a trusted source installation.

### Memory, history, and revert

`remember` stores durable facts for future turns, `history_search` retrieves
prior conversations, and project `AGENTS.md`/`CLAUDE.md` files are injected as
workspace context. Memory, skills, and files are inspectable from native side
panels.

Revert/edit/regenerate can rewind a conversation to a user message and restore
before-images captured by `write_file` and `edit_file` (up to the configured
checkpoint limit). Arbitrary changes made by shell commands cannot be
checkpointed, and the UI states that boundary before destructive rewind.

## Data and configuration

Writable state is per-user:

- Windows: `%LOCALAPPDATA%\LittleHarness`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/LittleHarness`
- macOS: `~/Library/Application Support/LittleHarness`

It contains sessions, queue state, settings, memory, learned skills, the
managed browser profile, and the fallback workspace. Older project-local data
is migrated on first start.

Important overrides:

- `LMH_BASE_URL`, `LMH_MODEL`, `LMH_API_KEY`
- `LMH_WORKSPACE`, `LMH_DATA_DIR`
- `LMH_DISABLE_COMPUTER_USE`, `LMH_COMPUTER_USE_BIN`
- `LMH_ALLOW_REMOTE_READER=1` opts into forwarding query-free public URLs to
  the third-party Jina reader when direct page extraction fails (off by default)
- `LMH_NO_WINDOW=1` for compatibility server-only mode

A repository-local `harness.toml` can set fields from `harness/config.py`.

## Build and release

```powershell
# Windows x64 app plus Inno Setup installer
powershell -File packaging\build_windows.ps1
```

```bash
# Linux x86_64 AppImage
bash packaging/build_appimage.sh

# macOS app and DMG; run on the target Mac architecture
bash packaging/build_macos.sh
```

`.github/workflows/build.yml` tests and packages every push to `main` on
native runners. A semantic tag such as `v2.1.0` publishes a GitHub release
containing:

- `LittleHarness-Setup.exe`
- `LittleHarness-x86_64.AppImage`
- `LittleHarness-macOS-arm64.dmg`
- `LittleHarness-macOS-x86_64.dmg`
- `SHA256SUMS.txt`

The package bundles Qt, helper libraries, skills, and the current-platform
computer-use runtime. It does not require a separate Python installation.
The optional `LittleHarnessCLI` executable runs helper scripts and server-only
diagnostics without turning the native desktop into a web client.

## Repository layout

```text
harness/
  native/          PySide6 desktop application and in-process service facade
  agent.py         model/tool loop, steering, stop propagation
  context.py       budget enforcement, fading, compaction
  browser.py       persistent managed browser worker
  skills.py        catalog, routing, loading, learned-skill persistence
  mcp_client.py    persistent stdio MCP client
  tools/           file, shell, web, browser, computer, memory tools
  server.py        domain/session/job layer plus compatibility HTTP API
  tui.py           terminal client
web/index.html     legacy browser client
skills/            bundled SKILL.md packages and helper scripts
packaging/         PyInstaller, AppImage, Inno Setup, and DMG builds
tests/             unit, integration, contract, and packaging-facing checks
```

## Safety boundaries

`run`, `computer`, browser interactions, and MCP servers act with the current
user's permissions. Review consequential operations and stop a turn that is
heading in the wrong direction. Page content, fetched text, attachments, and
tool output are treated as untrusted data, but a local model can still make
mistakes.

The managed browser only navigates public HTTP(S) hosts and rejects embedded
credentials, localhost, and private network destinations. Local UI testing is
handled separately by `visual_check`. Install only MCP servers you trust and
scope filesystem servers to the required folders.

macOS requires Accessibility and Screen Recording consent for computer
control. Linux requires a signed-in graphical session with AT-SPI and session
D-Bus. Windows automation must run in the signed-in interactive desktop rather
than as a service. Readiness errors are returned to the model; the harness does
not encourage coordinate guessing when semantic control is unavailable.
