"""Stealth browser search & fetch (ported from lm-chat-proxy.js).

Drives ONE real Chrome/Edge on this machine via Playwright:
- multi-engine search with fallback: DuckDuckGo -> Bing -> Brave
- pages rendered in a real browser (JS sites work; far fewer bot blocks)
- Reddit read via the native .json endpoint from inside a real page
- persistent profile (cookies survive), ad/tracker hosts aborted

Playwright's sync API needs a single owning thread, so a dedicated worker
thread holds the browser and serves jobs from a queue. If Playwright or a
browser isn't available, callers fall back to the plain httpx path.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import queue
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import (parse_qs, parse_qsl, quote_plus, unquote, urlencode,
                          urlsplit, urlunsplit)

from .config import BROWSER_PROFILE_DIR

# A current stable-Chrome UA (no "Headless" token — the loudest bot tell).
# Overriding it also lets us send matching Sec-CH-UA client hints below.
STEALTH_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CLIENT_HINTS = {
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not?A_Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def _unwrap(href: str) -> str:
    """Bing/DDG wrap results in redirector URLs — recover the real target."""
    try:
        parts = urlsplit(href)
    except ValueError:
        return href
    host = (parts.hostname or "").lower()
    if host.endswith("bing.com") and parts.path.startswith("/ck/"):
        u = parse_qs(parts.query).get("u", [""])[0]
        if u.startswith("a1"):
            try:
                pad = u[2:] + "=" * (-len(u[2:]) % 4)
                return base64.urlsafe_b64decode(pad).decode("utf-8", "replace")
            except Exception:
                return href
    if "duckduckgo.com" in host and "uddg=" in parts.query:
        u = parse_qs(parts.query).get("uddg", [""])[0]
        if u:
            return unquote(u)
    return href

PROFILE_DIR = BROWSER_PROFILE_DIR
NAV_TIMEOUT = 30_000
MAX_CONTENT = 24_000

AD_HOSTS = {
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com", "adnxs.com",
    "amazon-adsystem.com", "connect.facebook.net", "scorecardresearch.com",
    "taboola.com", "outbrain.com", "criteo.com", "pubmatic.com",
    "rubiconproject.com", "openx.net", "moatads.com", "hotjar.com",
    "mixpanel.com", "segment.com", "popads.net", "propellerads.com",
}
_PUBLIC_HOST_CACHE: dict[str, bool] = {}


def _host_is_public(host: str) -> bool:
    host = host.rstrip(".").lower()
    if not host or host == "localhost" or host.endswith((".localhost", ".local")):
        return False
    if host in _PUBLIC_HOST_CACHE:
        return _PUBLIC_HOST_CACHE[host]
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(
            host, None, type=socket.SOCK_STREAM)}
        allowed = bool(addresses) and all(
            ipaddress.ip_address(address).is_global for address in addresses)
    except (socket.gaierror, ValueError):
        allowed = False
    _PUBLIC_HOST_CACHE[host] = allowed
    return allowed

# webdriver flag is the loudest tell; the rest comes from using a real
# channel browser (real UA + client hints) and AutomationControlled off.
STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
if (!window.chrome) window.chrome = { runtime: {} };
"""

CHALLENGE_RE = re.compile(
    r"unusual traffic|are you a robot|/sorry/index|captcha-delivery"
    r"|checking your browser|press & hold|verify you are human", re.I)

ENGINES = [
    ("duckduckgo",
     lambda q: "https://html.duckduckgo.com/html/?kl=us-en&q=" + quote_plus(q),
     """() => {
        const out = [];
        document.querySelectorAll('.result').forEach((el) => {
          if (out.length >= 8 || el.classList.contains('result--ad')) return;
          const a = el.querySelector('.result__a');
          if (!a) return;
          let href = a.getAttribute('href') || '';
          const m = href.match(/[?&]uddg=([^&]+)/);
          if (m) { try { href = decodeURIComponent(m[1]); } catch (e) {} }
          if (href.startsWith('//')) href = 'https:' + href;
          if (!/^https?:/.test(href)) return;
          out.push({ title: a.textContent.trim(), url: href,
            snippet: (el.querySelector('.result__snippet') || {}).textContent?.trim() || '' });
        });
        return out;
      }"""),
    ("bing",
     lambda q: "https://www.bing.com/search?setmkt=en-US&q=" + quote_plus(q),
     """() => {
        const out = [];
        document.querySelectorAll('li.b_algo').forEach((el) => {
          if (out.length >= 8) return;
          const a = el.querySelector('h2 a');
          if (!a || !/^https?:/.test(a.href)) return;
          const sn = el.querySelector('.b_caption p, .b_algoSlug, p');
          out.push({ title: a.textContent.trim(), url: a.href,
                     snippet: sn ? sn.textContent.trim() : '' });
        });
        return out;
      }"""),
    ("brave",
     lambda q: "https://search.brave.com/search?source=web&q=" + quote_plus(q),
     """() => {
        const out = [];
        document.querySelectorAll('#results [data-type="web"], #results .snippet').forEach((el) => {
          if (out.length >= 8) return;
          const a = el.querySelector('a[href^="http"]');
          if (!a) return;
          const titleEl = el.querySelector('.title, .snippet-title') || a;
          const sn = el.querySelector('.snippet-description, .snippet-content');
          const title = titleEl.textContent.trim();
          if (!title) return;
          out.push({ title, url: a.href, snippet: sn ? sn.textContent.trim() : '' });
        });
        return out;
      }"""),
]

EXTRACT_JS = """() => {
  const clone = document.cloneNode(true);
  clone.querySelectorAll(
    'script,style,noscript,svg,iframe,nav,footer,header,form,aside,[aria-hidden="true"],' +
    '[class*="cookie"],[class*="banner"],[class*="advert"],[id*="advert"]'
  ).forEach((el) => el.remove());
  const cands = [];
  clone.querySelectorAll('article, main, [role="main"], body').forEach((el) => {
    cands.push({ el, len: (el.innerText || '').length });
  });
  cands.sort((a, b) => b.len - a.len);
  const root = (cands[0] && cands[0].el) || clone.body;
  const content = (root.innerText || '').replace(/[ \\t]+/g, ' ')
    .replace(/\\n{3,}/g, '\\n\\n').trim();
  const meta = (sel, attr) => { const e = document.querySelector(sel); return e ? e.getAttribute(attr) : ''; };
  const title = meta('meta[property="og:title"]', 'content') || document.title || '';
  return { title: title.trim(), content };
}"""


class _BrowserWorker:
    """Owns the Playwright browser on its own thread; serves jobs via queue."""

    def __init__(self) -> None:
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.status = "cold"  # cold | ready | unavailable

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.status = "unavailable"
            self._drain("browser support not installed")
            return
        try:
            with sync_playwright() as pw:
                ctx = self._launch(pw)
                self.status = "ready"
                while True:
                    job = self._jobs.get()
                    if job is None:
                        break
                    fn, out = job
                    try:
                        out.put(("ok", fn(ctx)))
                    except Exception as e:
                        out.put(("err", f"{type(e).__name__}: {e}"))
                ctx.close()
        except Exception as e:
            self.status = "unavailable"
            self._drain(str(e))

    def _drain(self, msg: str) -> None:
        while True:
            try:
                job = self._jobs.get_nowait()
                if job is None:
                    continue
                _, out = job
                out.put(("err", msg))
            except queue.Empty:
                return

    def _launch(self, pw):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        opts = dict(
            headless=True,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=STEALTH_UA,
            extra_http_headers=CLIENT_HINTS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = None
        # real installed browsers first: genuine UA + client hints, no download
        for channel in ("chrome", "msedge", None):
            try:
                if channel:
                    ctx = pw.chromium.launch_persistent_context(
                        str(PROFILE_DIR), channel=channel, **opts)
                else:
                    ctx = pw.chromium.launch_persistent_context(
                        str(PROFILE_DIR), **opts)
                break
            except Exception:
                continue
        if ctx is None:
            raise RuntimeError("no Chromium-family browser available")
        ctx.add_init_script(STEALTH_INIT)
        ctx.set_default_timeout(NAV_TIMEOUT)

        def block_ads(route):
            parsed = urlsplit(route.request.url)
            host = parsed.hostname or ""
            if parsed.scheme in {"http", "https"} and not _host_is_public(host):
                return route.abort()
            parts = host.lower().split(".")
            for i in range(len(parts) - 1):
                if ".".join(parts[i:]) in AD_HOSTS:
                    return route.abort()
            return route.continue_()

        ctx.route("**/*", block_ads)
        return ctx

    def submit(self, fn, timeout: float = 75.0,
               stop_event: threading.Event | None = None):
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("browser action stopped by user")
        self._ensure_thread()
        out: queue.Queue = queue.Queue()
        self._jobs.put((fn, out))
        deadline = time.monotonic() + timeout
        while True:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("browser action stopped by user")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("browser job timed out")
            try:
                kind, val = out.get(timeout=min(0.25, remaining))
                break
            except queue.Empty:
                if self.status == "unavailable" and (
                        self._thread is None or not self._thread.is_alive()):
                    raise RuntimeError("browser support is unavailable")
        if kind == "err":
            raise RuntimeError(val)
        return val

    def close(self, timeout: float = 5.0) -> None:
        """Shut down Playwright and its browser process, if one was started."""
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._thread = None
                self.status = "cold"
                return
            self._jobs.put(None)
        thread.join(timeout=timeout)
        with self._lock:
            if not thread.is_alive() and self._thread is thread:
                self._thread = None
                self.status = "cold"


_worker = _BrowserWorker()


def close() -> None:
    _worker.close()


def available() -> bool:
    try:
        import playwright  # noqa: F401
        return _worker.status != "unavailable"
    except ImportError:
        return False


def _with_page(ctx, fn):
    page = ctx.new_page()
    try:
        return fn(page)
    finally:
        try:
            page.close()
        except Exception:
            pass


def search(query: str) -> list[dict]:
    """Multi-engine browser search. Raises on total failure."""
    def job(ctx):
        def run(page):
            last = "no results"
            for name, url_fn, parse_js in ENGINES:
                try:
                    page.goto(url_fn(query), wait_until="domcontentloaded")
                    page.wait_for_timeout(600)
                    if CHALLENGE_RE.search(page.content() or ""):
                        last = f"{name}: challenge page"
                        continue
                    results = page.evaluate(parse_js)
                    if results:
                        for r in results:
                            r["url"] = _unwrap(r["url"])
                        return results[:8]
                    last = f"{name}: 0 results"
                except Exception as e:
                    last = f"{name}: {e}"
            raise RuntimeError(last)
        return _with_page(ctx, run)
    return _worker.submit(job)


def _is_reddit(url: str) -> bool:
    host = (urlsplit(url).hostname or "").replace("www.", "")
    return host == "reddit.com" or host.endswith(".reddit.com")


def _fetch_reddit(page, url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    html_url = urlunsplit(("https", "old.reddit.com", path or "/", "", ""))
    json_url = urlunsplit(("https", "old.reddit.com",
                           (path or "") + ".json", "raw_json=1&limit=60", ""))
    page.goto(html_url, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    grab = page.evaluate(
        """async (ju) => {
          try { const r = await fetch(ju, {headers:{Accept:'application/json'},credentials:'include'});
                if (!r.ok) return null; return await r.text(); }
          catch (e) { return null; }
        }""", json_url)
    if grab:
        try:
            return _format_reddit(json.loads(grab))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    ex = page.evaluate(EXTRACT_JS)
    return (f"# {ex['title']}\n\n{ex['content']}")


def _format_reddit(data) -> str:
    lines: list[str] = []
    if (isinstance(data, list) and data and isinstance(data[0], dict)
            and data[0].get("data", {}).get("children")):
        post = data[0]["data"]["children"][0]["data"]
        lines.append(f"# {post.get('title', '')}")
        lines.append(f"r/{post.get('subreddit')} - u/{post.get('author')} - "
                     f"score {post.get('score')} - {post.get('num_comments')} comments")
        if post.get("selftext"):
            lines.append("\n" + post["selftext"].strip())
        lines.append("\n## Top comments\n")
        flat: list[tuple] = []

        def walk(children, depth):
            for c in children or []:
                d = c.get("data") or {}
                if c.get("kind") != "t1" or d.get("body") is None:
                    continue
                flat.append((depth, d.get("author"), d.get("score") or 0,
                             d["body"].strip()))
                replies = d.get("replies")
                if isinstance(replies, dict):
                    walk(replies.get("data", {}).get("children"), depth + 1)
        if len(data) > 1:
            walk(data[1].get("data", {}).get("children"), 0)
        flat.sort(key=lambda c: (c[0], -c[2]))
        for depth, author, score, body in flat[:40]:
            indent = "  " * min(depth, 4)
            lines.append(f"{indent}- u/{author} ({score}): "
                         + " ".join(body.split()))
        return "\n".join(lines)
    # listing
    children = (data.get("data", {}).get("children", [])
                if isinstance(data, dict) else [])
    posts = [c["data"] for c in children if c.get("kind") == "t3"]
    lines.append(f"Reddit listing - {len(posts)} posts")
    for p in posts[:25]:
        lines.append(f"\n- {p.get('title')}")
        lines.append(f"  r/{p.get('subreddit')} - score {p.get('score')} - "
                     f"{p.get('num_comments')} comments")
        lines.append(f"  https://www.reddit.com{p.get('permalink', '')}")
    return "\n".join(lines)


def fetch(url: str) -> str:
    """Render a page in the real browser and return readable text."""
    def job(ctx):
        def run(page):
            if _is_reddit(url):
                return _fetch_reddit(page, url)[:MAX_CONTENT]
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(700)
            ex = page.evaluate(EXTRACT_JS)
            body = (f"# {ex['title']}\n\n" if ex["title"] else "") + ex["content"]
            return body[:MAX_CONTENT]
        return _with_page(ctx, run)
    return _worker.submit(job)


CONTROL_STATE_JS = r"""() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' &&
      s.display !== 'none' && Number(s.opacity || 1) > 0;
  };
  document.querySelectorAll('[data-lmh-ref]').forEach(el =>
    el.removeAttribute('data-lmh-ref'));
  const selector = 'a[href],button,input,textarea,select,summary,[role="button"],' +
    '[role="link"],[role="tab"],[contenteditable="true"]';
  const elements = [];
  for (const el of document.querySelectorAll(selector)) {
    if (!visible(el) || elements.length >= 80) continue;
    const ref = `e${elements.length + 1}`;
    el.setAttribute('data-lmh-ref', ref);
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const inputType = (el.getAttribute('type') || '').toLowerCase();
    const autocomplete = (el.getAttribute('autocomplete') || '').toLowerCase();
    const secret = inputType === 'password' ||
      /(?:password|cc-number|cc-csc)/.test(autocomplete);
    const rawValue = secret ? '' : el.value;
    const name = (el.getAttribute('aria-label') || el.getAttribute('title') ||
      el.getAttribute('placeholder') || el.innerText || rawValue ||
      el.getAttribute('alt') || '').replace(/\s+/g, ' ').trim().slice(0, 160);
    const value = secret ? '[redacted]' :
      (['INPUT','TEXTAREA','SELECT'].includes(el.tagName)
        ? String(el.value || '').slice(0, 120) : '');
    elements.push({ref, role, name, value, disabled: !!el.disabled});
  }
  const main = document.querySelector('main,article,[role="main"]') || document.body;
  const text = (main?.innerText || '').replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n').trim().slice(0, 5000);
  return {url: location.href, title: document.title || '', elements, text};
}"""


def _control_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = "https://" + url
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("invalid browser URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("browser navigation requires an http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("browser URLs cannot contain credentials")
    if not _host_is_public(parsed.hostname):
        raise ValueError("browser navigation only permits public hosts")
    return url


def _control_page(ctx):
    pages = [page for page in ctx.pages if not page.is_closed()]
    if pages:
        return pages[-1]
    return ctx.new_page()


def _format_control_state(state: dict) -> str:
    lines = [f"Page: {state.get('title') or '(untitled)'}",
             f"URL: {_redact_control_url(str(state.get('url', '')))}"]
    elements = state.get("elements") or []
    if elements:
        lines.append("Interactive elements (use the exact ref):")
        for item in elements:
            suffix = f" value={item['value']!r}" if item.get("value") else ""
            disabled = " disabled" if item.get("disabled") else ""
            lines.append(
                f"{item['ref']} {item['role']} {item['name']!r}{suffix}{disabled}")
    body = str(state.get("text") or "")
    if body:
        lines.extend(("Page text:", body))
    return "\n".join(lines)[:MAX_CONTENT]


def _redact_control_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url[:1000]
    sensitive = re.compile(
        r"(?:token|secret|password|passwd|session|auth|signature|credential|code)",
        re.IGNORECASE)

    def redact(component: str) -> str:
        if "=" not in component:
            return component
        return urlencode([
            (key, "[redacted]" if sensitive.search(key) else value)
            for key, value in parse_qsl(component, keep_blank_values=True)
        ])

    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       redact(parsed.query), redact(parsed.fragment)))[:1000]


def control(action: str, *, url: str | None = None, ref: str | None = None,
            text: str | None = None, key: str | None = None,
            direction: str = "down", amount: int = 650,
            x: float | None = None, y: float | None = None,
            wait_ms: int = 500, screenshot_dir: Path | None = None,
            stop_event: threading.Event | None = None) -> str:
    """Operate one persistent, sandboxed browser page and return fresh state.

    The returned MCP-compatible image marker lets the existing agent image
    pipeline attach the screenshot to vision-capable models without adding a
    second image protocol.

    ``click_at`` and ``type_text`` exist for the native browser panel, which
    interacts with the live screenshot by viewport coordinates and keyboard
    instead of semantic refs.
    """
    allowed = {"open", "state", "click", "type", "press", "select",
               "scroll", "back", "forward", "reload", "wait", "screenshot",
               "click_at", "type_text"}
    if action not in allowed:
        return f"Error: unknown browser action {action!r}."
    if action == "open" and not url:
        return "Error: browser open requires url."
    if action == "click_at" and (x is None or y is None):
        return "Error: browser click_at requires x and y."
    if action == "type_text" and not text:
        return "Error: browser type_text requires text."
    safe_url: str | None = None
    if action == "open":
        try:
            safe_url = _control_url(str(url))
        except ValueError as exc:
            return f"Error: {exc}"
    if action in {"click", "type", "select"} and not ref:
        return f"Error: browser {action} requires ref from the latest state."
    if ref and not re.fullmatch(r"e[1-9][0-9]{0,2}", ref):
        return "Error: browser ref must look like e1 and come from the latest state."
    if action in {"type", "select"} and text is None:
        return f"Error: browser {action} requires text."
    wait_ms = min(max(int(wait_ms), 0), 10_000)
    amount = min(max(int(amount), 50), 5000)

    def job(ctx):
        page = _control_page(ctx)
        if action == "open":
            page.goto(str(safe_url), wait_until="domcontentloaded")
        elif action == "click":
            page.locator(f'[data-lmh-ref="{ref}"]').click()
        elif action == "type":
            target = page.locator(f'[data-lmh-ref="{ref}"]')
            target.fill(str(text))
        elif action == "select":
            page.locator(f'[data-lmh-ref="{ref}"]').select_option(label=str(text))
        elif action == "press":
            if not key:
                raise ValueError("browser press requires key")
            page.keyboard.press(key)
        elif action == "click_at":
            size = page.viewport_size or {"width": 1280, "height": 720}
            px = float(x if x is not None else 0.0)
            py = float(y if y is not None else 0.0)
            page.mouse.click(min(max(px, 0.0), size["width"] - 1),
                             min(max(py, 0.0), size["height"] - 1))
        elif action == "type_text":
            page.keyboard.type(str(text), delay=12)
        elif action == "scroll":
            delta = amount if direction == "down" else -amount
            if direction in {"left", "right"}:
                page.mouse.wheel(delta if direction == "right" else -delta, 0)
            else:
                page.mouse.wheel(0, delta)
        elif action == "back":
            page.go_back(wait_until="domcontentloaded")
        elif action == "forward":
            page.go_forward(wait_until="domcontentloaded")
        elif action == "reload":
            page.reload(wait_until="domcontentloaded")
        if wait_ms:
            page.wait_for_timeout(wait_ms)
        state = page.evaluate(CONTROL_STATE_JS)
        image = page.screenshot(type="jpeg", quality=72)
        saved = None
        if screenshot_dir is not None:
            output = screenshot_dir.resolve() / ".lmh" / "browser"
            output.mkdir(parents=True, exist_ok=True)
            saved = output / "current.jpg"
            saved.write_bytes(image)
        report = _format_control_state(state)
        if saved is not None:
            report += f"\nBrowser screenshot: {saved}"
        payload = {
            "report": report,
            "images": [{"data": base64.b64encode(image).decode("ascii"),
                        "mimeType": "image/jpeg"}],
        }
        return "__MCP_IMAGE_RESULT__:" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"))

    if stop_event is not None and stop_event.is_set():
        return "Error: browser action stopped by user."
    try:
        return _worker.submit(job, stop_event=stop_event)
    except InterruptedError:
        return "Error: browser action stopped by user."
    except Exception as exc:
        return f"Error: browser {action} failed: {type(exc).__name__}: {exc}"


def self_test() -> dict:
    def job(ctx):
        def run(page):
            page.goto("https://example.com/", wait_until="domcontentloaded")
            fp = page.evaluate("""() => ({
              userAgent: navigator.userAgent,
              webdriver: navigator.webdriver,
              hasChrome: !!window.chrome,
              languages: navigator.languages,
            })""")
            warnings = []
            if "Headless" in fp["userAgent"]:
                warnings.append("UA contains Headless")
            if fp["webdriver"]:
                warnings.append("navigator.webdriver leaks")
            if not fp["hasChrome"]:
                warnings.append("window.chrome missing")
            return {"fingerprint": fp, "warnings": warnings,
                    "verdict": "has tells" if warnings else "looks clean"}
        return _with_page(ctx, run)
    return _worker.submit(job)
