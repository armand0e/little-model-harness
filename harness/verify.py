"""Write-time verification: give the model feedback from reality the moment
it saves a file, at zero extra steps.

- .html  -> render at desktop + mobile sizes, capture screenshots, layout
            diagnostics, console errors, and failed resource loads
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
import sys
from pathlib import Path
from urllib.parse import urlsplit

# windowed app: console children must not pop terminal windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

MAX_CHECK_BYTES = 2_000_000
MAX_REPORT = 6000
VISUAL_MARKER = "__VISUAL_QA__:"
VIEWPORTS = {
    "desktop": (1440, 1000),
    "tablet": (900, 1100),
    "mobile": (390, 844),
}

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


def _viewport_names(spec: str) -> list[str]:
    names = [name.strip().lower() for name in spec.split(",") if name.strip()]
    valid = [name for name in names if name in VIEWPORTS]
    return list(dict.fromkeys(valid))[:3] or ["desktop", "mobile"]


def _qa_output_dir(root: Path) -> Path:
    output = root.resolve() / ".lmh" / "visual-qa"
    output.mkdir(parents=True, exist_ok=True)
    return output


def _cleanup_visual_qa(output: Path) -> None:
    try:
        shots = sorted(output.glob("*.png"), key=lambda p: p.stat().st_mtime,
                       reverse=True)
        for stale in shots[60:]:
            stale.unlink(missing_ok=True)
    except OSError:
        pass


def visual_check(target: str | Path, output_root: Path,
                 viewports: str = "desktop,mobile",
                 click_selector: str = "", scroll_selector: str = "",
                 state_label: str = "default", wait_ms: int = 700,
                 full_page: bool = False, stop_event=None) -> str:
    """Render a local HTML file or loopback URL and return screenshots + QA."""
    if stop_event is not None and stop_event.is_set():
        return "Error: visual verification stopped by user."
    browser_path = _find_browser()
    if not browser_path:
        return ("Visual QA unavailable: no Chrome, Edge, or Chromium executable "
                "was found. Do not claim the UI was visually verified.")
    raw_target = str(target)
    parsed = urlsplit(raw_target)
    target_name = "page"
    if parsed.scheme in {"http", "https"}:
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return "Error: visual_check only opens local files or loopback URLs."
        url = raw_target
        target_name = (parsed.path.rsplit("/", 1)[-1] or "page")
    else:
        path = Path(target).expanduser().resolve()
        if not path.is_file():
            return f"Error: visual target not found: {path}"
        if path.suffix.lower() not in {".html", ".htm"}:
            return "Error: visual_check currently supports HTML files and loopback URLs."
        if path.stat().st_size > MAX_CHECK_BYTES:
            return "Visual QA skipped: HTML is over the 2 MB direct-render limit."
        url, target_name = path.as_uri(), path.name

    safe_target = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(target_name).stem)[:40] or "page"
    safe_state = re.sub(r"[^a-zA-Z0-9_-]+", "-", state_label)[:30] or "default"
    output = _qa_output_dir(output_root)
    selected = _viewport_names(viewports)
    wait_ms = max(0, min(int(wait_ms), 10_000))
    screenshots: list[dict] = []
    reports: list[str] = []
    all_errors: list[str] = []

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, executable_path=browser_path,
                args=["--disable-gpu"])
            try:
                for name in selected:
                    if stop_event is not None and stop_event.is_set():
                        return "Error: visual verification stopped by user."
                    width, height = VIEWPORTS[name]
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        device_scale_factor=1)
                    page = context.new_page()
                    errors: list[str] = []

                    def on_console(msg):
                        if msg.type == "error":
                            errors.append(f"console.{msg.type}: {msg.text}")

                    def on_page_error(exc):
                        errors.append(f"uncaught: {exc}")

                    def on_request_failed(request):
                        errors.append(
                            f"failed-to-load: {request.url} ({request.failure})")

                    page.on("console", on_console)
                    page.on("pageerror", on_page_error)
                    page.on("requestfailed", on_request_failed)
                    try:
                        page.goto(url, wait_until="load", timeout=15_000)
                        page.evaluate(
                            "() => document.fonts ? document.fonts.ready : Promise.resolve()")
                        if click_selector:
                            page.locator(click_selector).first.click(timeout=5000)
                        if scroll_selector:
                            page.locator(scroll_selector).first.scroll_into_view_if_needed(
                                timeout=5000)
                        # Short waits keep the Stop button responsive even
                        # when a page requests a long settle time.
                        remaining = wait_ms
                        while remaining > 0:
                            if stop_event is not None and stop_event.is_set():
                                return "Error: visual verification stopped by user."
                            chunk = min(remaining, 100)
                            page.wait_for_timeout(chunk)
                            remaining -= chunk
                        diag = page.evaluate("""() => {
                          const root = document.documentElement;
                          const body = document.body;
                          const relevantImages = [...document.images].filter(img =>
                            img.getAttribute('src') && img.getClientRects().length > 0);
                          const broken = relevantImages.filter(
                            img => img.complete && img.naturalWidth === 0).length;
                          const overflow = Math.max(root.scrollWidth, body?.scrollWidth || 0)
                            - root.clientWidth;
                          const visibleText = (body?.innerText || '').trim().length;
                          return {title: document.title || '(untitled)',
                            pageWidth: Math.max(root.scrollWidth, body?.scrollWidth || 0),
                            pageHeight: Math.max(root.scrollHeight, body?.scrollHeight || 0),
                            overflow: Math.max(0, overflow), brokenImages: broken,
                            visibleText, images: relevantImages.length};
                        }""")
                        shot_path = output / f"{safe_target}-{safe_state}-{name}.png"
                        page.screenshot(path=str(shot_path), full_page=bool(full_page),
                                        animations="disabled")
                        screenshots.append({"path": str(shot_path), "label": name})
                        issue_bits = []
                        if diag["overflow"]:
                            issue_bits.append(f"HORIZONTAL OVERFLOW {diag['overflow']}px")
                        if diag["brokenImages"]:
                            issue_bits.append(f"BROKEN IMAGES {diag['brokenImages']}")
                        if diag["visibleText"] == 0:
                            issue_bits.append("NO VISIBLE TEXT")
                        suffix = "; " + ", ".join(issue_bits) if issue_bits else ""
                        reports.append(
                            f"- {name} {width}x{height}: document "
                            f"{diag['pageWidth']}x{diag['pageHeight']}, "
                            f"{diag['images']} image(s){suffix}")
                    except Exception as exc:
                        errors.append(f"render failed: {type(exc).__name__}: {exc}")
                        reports.append(f"- {name} {width}x{height}: RENDER FAILED")
                    finally:
                        all_errors.extend(f"{name}: {error}" for error in errors[:12])
                        context.close()
            finally:
                browser.close()
    except Exception as exc:
        return (f"Visual QA unavailable: {type(exc).__name__}: {exc}. "
                "Do not claim the UI was visually verified.")

    lines = [f"Visual QA rendered {target_name} in {len(screenshots)}/{len(selected)} "
             "requested viewport(s).", *reports]
    if all_errors:
        lines.append(f"Runtime/resource errors ({len(all_errors)}):")
        lines.extend(f"  - {error}" for error in all_errors[:12])
    else:
        lines.append("Runtime/resource check: no errors observed.")
    for shot_info in screenshots:
        lines.append(
            f"Visual screenshot [{shot_info['label']}]: {shot_info['path']}")
    if screenshots:
        lines.append(
            "Inspect every attached screenshot for hierarchy, spacing, clipping, "
            "contrast, responsiveness, and visual polish. Fix issues and run "
            "visual_check again; a clean console alone is not visual verification.")
    _cleanup_visual_qa(output)
    return VISUAL_MARKER + json.dumps(
        {"report": "\n".join(lines), "screenshots": screenshots},
        ensure_ascii=False)


def check_html(path: Path, visual_root: Path | None = None) -> str:
    return visual_check(path, visual_root or path.parent,
                        viewports="desktop,mobile", state_label="auto")


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


def check_written_file(path: Path, visual_root: Path | None = None) -> str | None:
    """Dispatch by extension; returns a short report or None."""
    ext = path.suffix.lower()
    report: str | None
    try:
        if ext in (".html", ".htm"):
            report = check_html(path, visual_root)
        elif ext == ".py":
            report = check_python(path)
        elif ext in (".js", ".mjs"):
            report = check_js(path)
        else:
            return None
    except Exception:
        return None
    if report and not report.startswith(VISUAL_MARKER) and len(report) > MAX_REPORT:
        report = report[:MAX_REPORT] + "…"
    return report
