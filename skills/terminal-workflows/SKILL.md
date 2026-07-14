---
name: terminal-workflows
description: Execute reliable workspace-aware shell workflows with PowerShell on Windows and bash on Linux or macOS. Use for builds, tests, package managers, Git inspection, process diagnostics, project scripts, or command-line tools where real output and exit status are required.
---
Use `run` for bounded, non-interactive commands. It starts in the conversation
workspace, returns stdout, stderr, and the exit code, and is cancelled when the
user stops the turn.

Workflow:
1. Inspect the repository with file tools before choosing commands. Prefer
   targeted commands over broad scans.
2. Run the smallest command that proves or disproves the current hypothesis.
3. Read stderr and the exit code. Do not treat partial output as success.
4. Fix the concrete failure, then rerun the relevant check. End with the
   narrowest meaningful test plus the project-wide check when risk warrants it.

Rules:
- Use PowerShell syntax on Windows and bash syntax on Linux/macOS. Avoid
  cross-shell escaping tricks.
- Prefer `read_file`, `search`, `write_file`, and `edit_file` for file work;
  use the terminal for tools that genuinely need a process.
- Avoid interactive prompts. Pass non-interactive flags and explicit paths.
- Give long-running commands a realistic `timeout_seconds`, up to 300.
- Start local development servers only when needed for verification and stop
  them when finished. Never leave accidental background processes behind.
- Never run destructive reset, recursive deletion, credential, publish, or
  deployment commands unless the user explicitly authorized that scope.
- If output is truncated, rerun a narrower command or write tool output to a
  workspace artifact and inspect the relevant section.
