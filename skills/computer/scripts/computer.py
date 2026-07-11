"""Desktop control helper (Windows / macOS / Linux).

Usage: python computer.py <command> [args...]
"""
import os
import platform
import subprocess
import sys
import time

_SYS = platform.system()
_WIN, _MAC = _SYS == "Windows", _SYS == "Darwin"

# window titles often contain unicode the default cp1252 console can't print
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def _pyautogui():
    import pyautogui
    pyautogui.FAILSAFE = True
    return pyautogui


# ---------- macOS permissions (TCC) ----------
# Synthetic clicks/keys need Accessibility; screenshots need Screen
# Recording. Both are granted per-app in System Settings > Privacy &
# Security. Checking first turns silent failures into clear instructions.
def _mac_accessibility_ok(prompt=False) -> bool:
    try:
        from ApplicationServices import (AXIsProcessTrusted,
                                         AXIsProcessTrustedWithOptions)
        if prompt:
            try:
                from ApplicationServices import kAXTrustedCheckOptionPrompt
                return bool(AXIsProcessTrustedWithOptions(
                    {kAXTrustedCheckOptionPrompt: True}))
            except Exception:
                pass
        return bool(AXIsProcessTrusted())
    except Exception:
        return True  # can't check — let the action try


def _mac_screen_ok(prompt=False) -> bool:
    try:
        import Quartz
        if prompt and not Quartz.CGPreflightScreenCaptureAccess():
            Quartz.CGRequestScreenCaptureAccess()
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return True


_MAC_AX_HELP = (
    "macOS is blocking keyboard/mouse control: grant ACCESSIBILITY access in "
    "System Settings > Privacy & Security > Accessibility (add/enable "
    "'Little Harness'), then retry. A permission prompt may be on screen now. "
    "Tell the user to do this — it cannot be done programmatically.")
_MAC_SCREEN_HELP = (
    "macOS is blocking screenshots: grant SCREEN RECORDING access in System "
    "Settings > Privacy & Security > Screen Recording (add/enable 'Little "
    "Harness'), then retry. A permission prompt may be on screen now. "
    "Tell the user to do this — it cannot be done programmatically.")


def _need_ax():
    if _MAC and not _mac_accessibility_ok(prompt=True):
        sys.exit(_MAC_AX_HELP)


def cmd_checkperms():
    if not _MAC:
        print("No special permissions needed on this OS.")
        return
    ax = _mac_accessibility_ok(prompt=True)
    scr = _mac_screen_ok(prompt=True)
    print(f"Accessibility (type/click/press): {'granted' if ax else 'NOT granted'}")
    print(f"Screen Recording (screenshots):   {'granted' if scr else 'NOT granted'}")
    if not (ax and scr):
        print("Ask the user to enable 'Little Harness' in System Settings > "
              "Privacy & Security > Accessibility and > Screen Recording, "
              "then retry. macOS may have just shown them a prompt.")


# ---------- commands ----------
def cmd_open(target):
    if _WIN:
        try:
            os.startfile(target)  # noqa: S606 - intentional
            print(f"Opened {target}")
            return
        except OSError:
            pass
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Start-Process '{target}'"],
                           capture_output=True, text=True)
    elif _MAC:
        # try as file/URL first, then as an application name
        r = subprocess.run(["open", target], capture_output=True, text=True)
        if r.returncode != 0:
            r = subprocess.run(["open", "-a", target],
                               capture_output=True, text=True)
    else:
        r = subprocess.run(["xdg-open", target], capture_output=True, text=True)
    if r.returncode == 0:
        print(f"Opened {target}")
    else:
        print(f"Could not open {target}: {(r.stderr or '').strip()}")


def _mac_windows():
    """(app name, window title) pairs via System Events. First use pops the
    'wants to control System Events' Automation prompt — the user must allow."""
    r = subprocess.run(["osascript", "-e",
                        'tell application "System Events"\n'
                        'set out to ""\n'
                        'repeat with p in (processes whose visible is true)\n'
                        'set pn to name of p\n'
                        'repeat with w in windows of p\n'
                        'set out to out & pn & " — " & (name of w) & linefeed\n'
                        'end repeat\nend repeat\nreturn out\nend tell'],
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if "not allowed" in err.lower() or "1743" in err:
            sys.exit("macOS blocked window listing: the user must allow "
                     "'Little Harness' to control 'System Events' in System "
                     "Settings > Privacy & Security > Automation (a prompt "
                     "may be on screen now), then retry.")
        sys.exit(f"Could not list windows: {err}")
    return [l for l in (r.stdout or "").splitlines() if l.strip()]


def cmd_windows():
    if _MAC:
        lines = _mac_windows()
        print("\n".join(f"- {l}" for l in lines[:40]) or "(no windows)")
        return
    import pygetwindow as gw
    titles = [t for t in gw.getAllTitles() if t.strip()]
    print("\n".join(f"- {t}" for t in titles[:40]) or "(no windows)")


def cmd_focus(title):
    if _MAC:
        lines = _mac_windows()
        match = next((l for l in lines if title.lower() in l.lower()), None)
        if not match:
            print(f"No window matching '{title}'. Use the windows command to list titles.")
            return
        app = match.split(" — ")[0].strip("- ").strip()
        r = subprocess.run(["osascript", "-e",
                            f'tell application "{app}" to activate'],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            time.sleep(0.4)
            print(f"Focused: {match.strip('- ')}")
        else:
            print(f"Could not focus {app}: {(r.stderr or '').strip()}")
        return
    import pygetwindow as gw
    wins = [w for w in gw.getAllWindows()
            if title.lower() in (w.title or "").lower()]
    if not wins:
        print(f"No window matching '{title}'. Use the windows command to list titles.")
        return
    w = wins[0]
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
    except Exception:
        # pygetwindow's activate can be flaky; alt-key nudge then retry
        pg = _pyautogui()
        pg.press("alt")
        w.activate()
    time.sleep(0.4)
    print(f"Focused: {w.title}")


def cmd_type(text):
    _need_ax()
    pg = _pyautogui()
    parts = text.replace("\\n", "\n").split("\n")
    for i, part in enumerate(parts):
        if part:
            pg.write(part, interval=0.02)
        if i < len(parts) - 1:
            pg.press("enter")
    print(f"Typed {len(text)} chars")


def cmd_press(keys):
    _need_ax()
    pg = _pyautogui()
    combo = [k.strip().lower() for k in keys.split("+")]
    if _MAC:
        # the standard shortcut modifier on macOS is command, not ctrl
        remap = {"ctrl": "command", "alt": "option", "win": "command"}
        combo = [remap.get(k, k) for k in combo]
    pg.hotkey(*combo) if len(combo) > 1 else pg.press(combo[0])
    print(f"Pressed {'+'.join(combo)}")


def cmd_click(x, y, button="left", clicks=1):
    _need_ax()
    pg = _pyautogui()
    pg.click(int(x), int(y), clicks=clicks, button=button)
    print(f"{button} click at ({x}, {y})")


def cmd_scroll(amount):
    _need_ax()
    pg = _pyautogui()
    pg.scroll(int(amount))
    print(f"Scrolled {amount}")


def cmd_screenshot(path=None):
    if _MAC and not _mac_screen_ok(prompt=True):
        sys.exit(_MAC_SCREEN_HELP)
    pg = _pyautogui()
    if not path:
        ws = os.environ.get("LMH_WORKSPACE") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))), "workspace")
        os.makedirs(ws, exist_ok=True)
        path = os.path.join(ws, "screenshot.png")
    img = pg.screenshot()
    img.save(path)
    print(f"Screenshot saved to {path} (screen is {img.width}x{img.height}). "
          f"Tell the user where it is — you cannot view it yourself.")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1].lower(), sys.argv[2:]
    if cmd == "open":
        cmd_open(" ".join(args))
    elif cmd == "windows":
        cmd_windows()
    elif cmd == "focus":
        cmd_focus(" ".join(args))
    elif cmd == "type":
        cmd_type(" ".join(args))
    elif cmd == "press":
        cmd_press(args[0])
    elif cmd == "click":
        cmd_click(args[0], args[1])
    elif cmd == "doubleclick":
        cmd_click(args[0], args[1], clicks=2)
    elif cmd == "rightclick":
        cmd_click(args[0], args[1], button="right")
    elif cmd == "scroll":
        cmd_scroll(args[0])
    elif cmd == "screenshot":
        cmd_screenshot(args[0] if args else None)
    elif cmd == "checkperms":
        cmd_checkperms()
    elif cmd == "wait":
        time.sleep(min(float(args[0]), 30))
        print(f"Waited {args[0]}s")
    else:
        sys.exit(f"Unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
