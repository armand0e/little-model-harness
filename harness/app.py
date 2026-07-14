"""Desktop entry point for the packaged app.

- Default: run the in-process PySide6/Qt desktop client. No localhost server
  is created for the desktop UI.
- `--server-only` (or LMH_NO_WINDOW=1): headless server, no window.
- `--runpy script.py [args]`: run a Python script inside the bundled
  interpreter — this is how skill helper scripts execute on machines
  with no Python installed (the `run` tool aliases `python` to this).
- `--pick-folder [start]`: native folder picker (used by the server).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from typing import Any

APP_NAME = "Little Harness"


def _runpy_mode() -> None:
    import runpy
    import traceback
    if len(sys.argv) < 3:
        print("usage: --runpy script.py [args]", file=sys.stderr)
        sys.exit(2)
    script = sys.argv[2]
    sys.argv = sys.argv[2:]  # the script sees itself as argv[0]
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        sys.exit(1)


def _pick_folder_mode() -> None:
    """Show the native folder picker and print the chosen path (used by
    the server's workspace chip when running as a packaged exe)."""
    import tkinter as tk
    import tkinter.filedialog as fd
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", 1)
    start = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~")
    print(fd.askdirectory(initialdir=start, mustexist=False,
                          title=f"Choose the {APP_NAME} workspace folder")
          or "")


def _free_port(preferred: int = 8321) -> int:
    for port in (preferred, 0):
        try:
            with socket.socket() as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


def _wait_ready(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _start_server(port: int) -> tuple[Any, threading.Thread]:
    """Run uvicorn in a daemon thread (it skips signal handlers off the
    main thread, so the window keeps the main thread)."""
    import uvicorn

    from .server import app, start_background_services

    start_background_services()

    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server, t


def _stop_server(server: Any, server_thread: threading.Thread) -> None:
    """Stop active generations and give persistence a chance to finish."""
    from . import browser
    from .mcp_client import MCP_HUB
    from .server import (MODEL_LOCK, SESSIONS, SESSIONS_LOCK,
                         begin_shutdown)

    begin_shutdown()
    with SESSIONS_LOCK:
        sessions = list(SESSIONS.values())
    for session in sessions:
        if session._job:
            session._job.cancel()
        elif session._agent:
            session._agent.request_stop()
    deadline = time.monotonic() + 5.0
    while MODEL_LOCK.locked() and time.monotonic() < deadline:
        time.sleep(0.05)
    browser.close()
    MCP_HUB.close()
    server.should_exit = True
    server_thread.join(timeout=5.0)


def main() -> None:
    # The console-subsystem twin executes helper scripts whose output can
    # contain any Unicode text.  Windows pipes otherwise default to a legacy
    # code page (often cp1252), which makes valid documents crash on print.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        elif hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) > 1 and sys.argv[1] == "--runpy":
        _runpy_mode()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--pick-folder":
        _pick_folder_mode()
        return

    from .instance import acquire_instance_lock
    if not acquire_instance_lock():
        print(f"{APP_NAME} is already running for this user data directory.",
              file=sys.stderr, flush=True)
        return

    headless = ("--server-only" in sys.argv[1:]
                or bool(os.environ.get("LMH_NO_WINDOW"))
                or bool(os.environ.get("LMH_NO_BROWSER")))  # back-compat

    if "--native-smoke" in sys.argv[1:]:
        from .native.app import smoke_native
        raise SystemExit(smoke_native())

    if headless:
        port = _free_port()
        url = f"http://127.0.0.1:{port}"
        server, server_thread = _start_server(port)
        if not _wait_ready(port):
            print(f"{APP_NAME} server failed to start on {url}", file=sys.stderr,
                  flush=True)
            server.should_exit = True
            server_thread.join(timeout=2.0)
            return
        print(f"{APP_NAME} server-only mode running at {url}", flush=True)
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            _stop_server(server, server_thread)
        return

    from .native import run_native
    try:
        run_native()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
