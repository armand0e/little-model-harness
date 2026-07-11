"""Desktop entry point for the packaged app.

- Default: run the server in a background thread and show the UI in a
  native desktop window (pywebview: WebView2 on Windows, Qt/GTK on
  Linux). Closing the window quits the app.
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
import webbrowser

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


def _start_server(port: int) -> threading.Thread:
    """Run uvicorn in a daemon thread (it skips signal handlers off the
    main thread, so the window keeps the main thread)."""
    import uvicorn

    from .server import app  # imports config → migrates data into appdata

    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return t


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--runpy":
        _runpy_mode()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--pick-folder":
        _pick_folder_mode()
        return

    # windowed (console=False) build: no console streams exist; give the
    # logging stack somewhere harmless to write
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    headless = ("--server-only" in sys.argv[1:]
                or bool(os.environ.get("LMH_NO_WINDOW"))
                or bool(os.environ.get("LMH_NO_BROWSER")))  # back-compat

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server_thread = _start_server(port)
    _wait_ready(port)
    print(f"{APP_NAME} running at {url}", flush=True)

    if headless:
        server_thread.join()
        return

    # ---- the app window ----
    try:
        import webview
        webview.create_window(APP_NAME, url, width=1360, height=880,
                              min_size=(920, 620), confirm_close=False,
                              text_select=True, zoomable=True)
        webview.start()          # blocks until the window is closed
    except Exception:
        # no webview backend on this machine — at least show the UI
        webbrowser.open(url)
        server_thread.join()
        return
    # window closed = quit; the server thread is a daemon
    os._exit(0)


if __name__ == "__main__":
    main()
