"""Shell execution tool: PowerShell on Windows, bash elsewhere."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

MAX_OUTPUT = 6000

_WINDOWS = platform.system() == "Windows"
# In the packaged (windowed) app, spawning a console program would pop a
# visible terminal window for every call — create them with no window.
CREATE_NO_WINDOW = 0x08000000 if _WINDOWS else 0

# Packaged app: there may be no python.exe on the machine, but skills say
# `python script.py`. Route that to our exe's --runpy mode, which runs the
# script inside the bundled interpreter (with all bundled libraries). The
# console-subsystem twin is used so the shell waits and captures output.
def _frozen_cli_exe() -> str:
    exe = Path(sys.executable)
    cli = exe.with_name("LittleHarnessCLI.exe" if _WINDOWS
                        else "LittleHarnessCLI")
    return str(cli if cli.exists() else exe)


if getattr(sys, "frozen", False):
    _CLI = _frozen_cli_exe()
    if _WINDOWS:
        _PY_SHIM = (f'function python {{ & "{_CLI}" --runpy @args }}; '
                    f'function python3 {{ & "{_CLI}" --runpy @args }}; ')
    else:
        _PY_SHIM = (f'python() {{ "{_CLI}" --runpy "$@"; }}; '
                    f'python3() {{ python "$@"; }}; ')
else:
    _PY_SHIM = ""


def run_command(command: str, timeout_seconds: int = 60,
                cwd: Path | None = None) -> str:
    timeout_seconds = min(max(timeout_seconds, 1), 300)
    env = None
    if cwd is not None:
        # skill helper scripts read LMH_WORKSPACE to know where output goes
        env = {**os.environ, "LMH_WORKSPACE": str(cwd)}
    argv = (["powershell", "-NoProfile", "-NonInteractive", "-Command",
             _PY_SHIM + command] if _WINDOWS
            else ["bash", "-c", _PY_SHIM + command])
    try:
        proc = subprocess.run(
            argv,
            capture_output=True, text=True, timeout=timeout_seconds,
            encoding="utf-8", errors="replace",
            cwd=str(cwd) if cwd is not None else None, env=env,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout_seconds}s."
    except FileNotFoundError:
        return ("Error: PowerShell not found." if _WINDOWS
                else "Error: bash not found.")
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"[stderr]\n{err}")
    parts.append(f"[exit code: {proc.returncode}]")
    result = "\n".join(parts)
    if len(result) > MAX_OUTPUT:
        result = (result[:MAX_OUTPUT // 2] + "\n...[output truncated]...\n"
                  + result[-MAX_OUTPUT // 2:])
    return result
