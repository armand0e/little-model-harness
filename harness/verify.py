"""Write-time verification: give the model feedback from reality the moment
it saves a file, at zero extra steps.

- .html  -> load in headless Chrome/Edge, capture console errors, uncaught
            exceptions, unhandled rejections, and failed resource loads
- .py    -> syntax check (py_compile)
- .js    -> node --check

All checks fail open: if the tooling isn't available the write succeeds
silently, exactly as before.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

# windowed app: console children must not pop terminal windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
import sys
import tempfile
from pathlib import Path

MAX_CHECK_BYTES = 2_000_000
MAX_REPORT = 900  # chars of check output appended to a tool result

# single line on purpose: keeps the page's own line numbers accurate
CAPTURE_SCRIPT = (
    '<script>(function(){var E=[];function add(k,m){E.push(k+": "+String(m)'
    '.slice(0,300));var el=document.getElementById("__lmh_errlog");if(!el){'
    'el=document.createElement("template");el.id="__lmh_errlog";'
    'document.documentElement.appendChild(el);}el.setAttribute("data-errors",'
    'JSON.stringify(E.slice(0,20)));}window.addEventListener("error",'
    'function(e){if(e.target&&(e.target.src||e.target.href)){add('
    '"failed-to-load",e.target.tagName+" "+(e.target.src||e.target.href));}'
    'else{add("uncaught-error",e.message+" (line "+(e.lineno||"?")+")");}},'
    'true);window.addEventListener("unhandledrejection",function(e){add('
    '"unhandled-rejection",e.reason);});var ce=console.error;console.error='
    'function(){add("console.error",Array.prototype.slice.call(arguments)'
    '.join(" "));if(ce)ce.apply(console,arguments);};})();</script>')


def _find_browser() -> str | None:
    for name in ("chrome", "msedge", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LocalAppData", "")
    for c in (
        rf"{pf}\Google\Chrome\Application\chrome.exe",
        rf"{pf86}\Google\Chrome\Application\chrome.exe",
        rf"{local}\Google\Chrome\Application\chrome.exe",
        rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
        rf"{pf}\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium",
    ):
        if Path(c).is_file():
            return c
    return None


def check_html(path: Path) -> str | None:
    """Render the page headlessly (over file://, like double-clicking it)
    and report what the browser console would show."""
    browser = _find_browser()
    if not browser or path.stat().st_size > MAX_CHECK_BYTES:
        return None
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # inject the capture script as early as possible
    m = re.search(r"<head[^>]*>", html, re.I)
    if m:
        wrapped = html[:m.end()] + CAPTURE_SCRIPT + html[m.end():]
    else:
        wrapped = CAPTURE_SCRIPT + html
    # same directory so relative src/href resolve identically
    tmp = (path.parent / f".__lmh_check__{path.name}").resolve()
    try:
        tmp.write_text(wrapped, encoding="utf-8")
        r = subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=4000", "--timeout=9000",
             "--dump-dom", tmp.as_uri()],
            capture_output=True, text=True, timeout=25,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW)
        dom = r.stdout or ""
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        tmp.unlink(missing_ok=True)
    m = re.search(r'id="__lmh_errlog"[^>]*data-errors="([^"]*)"', dom)
    if not m:
        # capture element only exists once an error happened
        return "Page check (headless browser): no console errors."
    try:
        errors = json.loads(m.group(1).replace("&quot;", '"')
                            .replace("&amp;", "&").replace("&lt;", "<")
                            .replace("&gt;", ">"))
    except json.JSONDecodeError:
        return None
    if not errors:
        return "Page check (headless browser): no console errors."
    listing = "\n".join(f"  - {e}" for e in errors[:8])
    note = ("\n  (checked over file:// — the same way a user double-clicks "
            "the file)") if "failed-to-load" in " ".join(errors) else ""
    return (f"Page check (headless browser) found {len(errors)} console "
            f"error(s) — fix them:\n{listing}{note}")


def check_python(path: Path) -> str | None:
    if getattr(sys, "frozen", False):
        # packaged app: no python.exe to shell out to — compile in-process
        try:
            compile(path.read_text(encoding="utf-8", errors="replace"),
                    str(path), "exec")
            return "Syntax check: OK."
        except SyntaxError as e:
            return f"Syntax check FAILED:\n{e.__class__.__name__}: {e}"
        except OSError:
            return None
    try:
        r = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                           capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace",
                           creationflags=CREATE_NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode == 0:
        return "Syntax check: OK."
    err = (r.stderr or r.stdout or "").strip()
    return f"Syntax check FAILED:\n{err}" if err else None


def check_js(path: Path) -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    try:
        r = subprocess.run([node, "--check", str(path)],
                           capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace",
                           creationflags=CREATE_NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode == 0:
        return "Syntax check (node): OK."
    err = (r.stderr or "").strip()
    return f"Syntax check (node) FAILED:\n{err}" if err else None


def check_written_file(path: Path) -> str | None:
    """Dispatch by extension; returns a short report or None."""
    ext = path.suffix.lower()
    try:
        if ext in (".html", ".htm"):
            report = check_html(path)
        elif ext == ".py":
            report = check_python(path)
        elif ext in (".js", ".mjs"):
            report = check_js(path)
        else:
            return None
    except Exception:
        return None
    if report and len(report) > MAX_REPORT:
        report = report[:MAX_REPORT] + "…"
    return report
