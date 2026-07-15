"""Interactive PTY shells for the web terminal panel.

The browser side runs xterm.js, so this module only has to pump raw bytes:
ConPTY (pywinpty) on Windows, openpty + subprocess elsewhere. Never
pty.fork(): forking a threaded server wedges the child on macOS.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


class WindowsConPty:
    def __init__(self, cwd: Path, cols: int, rows: int) -> None:
        from winpty import PtyProcess  # type: ignore[import-not-found]
        self._proc = PtyProcess.spawn(
            "powershell.exe -NoLogo", cwd=str(cwd), dimensions=(rows, cols))

    def read(self) -> str:
        return self._proc.read(4096)

    def write(self, data: str) -> None:
        self._proc.write(data)

    def resize(self, cols: int, rows: int) -> None:
        self._proc.setwinsize(rows, cols)

    def alive(self) -> bool:
        return self._proc.isalive()

    def close(self) -> None:
        try:
            self._proc.terminate(force=True)
        except Exception:
            pass


class UnixPty:
    def __init__(self, cwd: Path, cols: int, rows: int) -> None:
        import pty
        import subprocess
        shell = os.environ.get("SHELL", "/bin/bash")
        self._master, slave = pty.openpty()  # type: ignore[attr-defined]
        try:
            self._proc = subprocess.Popen(
                [shell], cwd=str(cwd),
                env={**os.environ, "TERM": "xterm-256color"},
                stdin=slave, stdout=slave, stderr=slave,
                start_new_session=True, close_fds=True)
        except BaseException:
            os.close(self._master)
            raise
        finally:
            os.close(slave)
        self.resize(cols, rows)

    def read(self) -> str:
        data = os.read(self._master, 4096)
        if not data:
            raise EOFError
        return data.decode("utf-8", errors="replace")

    def write(self, data: str) -> None:
        os.write(self._master, data.encode("utf-8"))

    def resize(self, cols: int, rows: int) -> None:
        import fcntl
        import struct
        import termios
        fcntl.ioctl(  # type: ignore[attr-defined]  # unix-only
            self._master, termios.TIOCSWINSZ,  # type: ignore[attr-defined]
            struct.pack("HHHH", rows, cols, 0, 0))

    def alive(self) -> bool:
        return self._proc.poll() is None

    def close(self) -> None:
        import signal
        try:
            os.killpg(self._proc.pid,  # type: ignore[attr-defined]
                      signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        try:
            self._proc.wait(timeout=1.5)
        except Exception:
            try:
                os.killpg(self._proc.pid,  # type: ignore[attr-defined]
                          signal.SIGKILL)  # type: ignore[attr-defined]
            except (OSError, ProcessLookupError):
                pass
        try:
            os.close(self._master)
        except OSError:
            pass


def spawn_shell(cwd: Path, cols: int = 100, rows: int = 30):
    """Spawn the platform shell in a real PTY rooted at ``cwd``."""
    cwd = Path(cwd)
    try:
        cwd.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if not cwd.is_dir():
        cwd = Path.home()
    backend = WindowsConPty if sys.platform == "win32" else UnixPty
    return backend(cwd, max(20, min(500, cols)), max(5, min(200, rows)))
