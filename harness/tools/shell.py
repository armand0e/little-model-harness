"""Shell execution tool: PowerShell on Windows, bash elsewhere."""
from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_OUTPUT = 6000

_WINDOWS = platform.system() == "Windows"
# In the packaged (windowed) app, spawning a console program would pop a
# visible terminal window for every call — create them with no window.
CREATE_NO_WINDOW = 0x08000000 if _WINDOWS else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if _WINDOWS else 0

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
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            proc = subprocess.Popen(
                argv, stdout=stdout, stderr=stderr,
                cwd=str(cwd) if cwd is not None else None, env=env,
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                start_new_session=not _WINDOWS,
            )
        except FileNotFoundError:
            return ("Error: PowerShell not found." if _WINDOWS
                    else "Error: bash not found.")
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            return f"Error: command timed out after {timeout_seconds}s."
        out = _bounded_capture(stdout).strip()
        err = _bounded_capture(stderr).strip()
    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"[stderr]\n{err}")
    parts.append(f"[exit code: {proc.returncode}]")
    result = "\n".join(parts)
    return result


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate the shell and descendants after a tool timeout."""
    if proc.poll() is not None:
        return
    try:
        if _WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, creationflags=CREATE_NO_WINDOW,
            )
        else:
            posix_os: Any = os
            posix_signal: Any = signal
            posix_os.killpg(proc.pid, posix_signal.SIGKILL)
        proc.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.SubprocessError:
            pass


def _bounded_capture(stream) -> str:
    """Read only the useful head/tail from a disk-backed process stream."""
    stream.flush()
    size = stream.tell()
    stream.seek(0)
    if size <= MAX_OUTPUT:
        data = stream.read()
    else:
        half = MAX_OUTPUT // 2
        head = stream.read(half)
        stream.seek(-half, os.SEEK_END)
        tail = stream.read(half)
        data = head + b"\n...[output truncated]...\n" + tail
    return data.decode("utf-8", errors="replace")
