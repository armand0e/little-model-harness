"""Web tools: search (keyless, free) and page fetch — no external parsing deps.

Search uses DuckDuckGo's HTML endpoints directly (we're server-side, so no
CORS games needed). Page fetch falls back to the keyless r.jina.ai reader
when a page yields no useful text (JS-heavy sites).
"""
from __future__ import annotations

import re
import ipaddress
import socket
import urllib.parse
from html.parser import HTMLParser

import httpx

MAX_TEXT = 6000
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LittleModelHarness"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "nav", "footer"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5",
               "h6", "section", "article", "blockquote", "pre", "table"}
MAX_REDIRECTS = 5


def _validate_public_url(url: str) -> str:
    """Reject credentials and local/private destinations in the web tool."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("only http:// and https:// URLs are supported")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing credentials are not allowed")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("local and private network URLs are not allowed")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(
            host, parts.port or (443 if parts.scheme == "https" else 80),
            type=socket.SOCK_STREAM)}
    except socket.gaierror as e:
        raise ValueError(f"could not resolve host {host}: {e}") from e
    if not addresses or any(not ipaddress.ip_address(addr).is_global
                            for addr in addresses):
        raise ValueError("local and private network URLs are not allowed")
    return urllib.parse.urlunsplit(parts)


def _get_with_safe_redirects(url: str, **kwargs) -> httpx.Response:
    current = _validate_public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = httpx.get(current, follow_redirects=False, **kwargs)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = _validate_public_url(urllib.parse.urljoin(current, location))
    raise httpx.TooManyRedirects("too many redirects")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data)


class _DDGResults(HTMLParser):
    """Extracts results from html.duckduckgo.com (a.result__a) or
    lite.duckduckgo.com (a.result-link) pages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._in_link = False
        self._in_snippet = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "a" and ("result__a" in cls or "result-link" in cls):
            href = a.get("href", "")
            m = re.search(r"[?&]uddg=([^&]+)", href)
            if m:
                href = urllib.parse.unquote(m.group(1))
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("http"):
                self.results.append({"title": "", "url": href, "snippet": ""})
                self._in_link = True
        elif "result__snippet" in cls and self.results:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False
        if tag in ("a", "td", "div") and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data):
        if not self.results:
            return
        if self._in_link:
            self.results[-1]["title"] += data
        elif self._in_snippet:
            self.results[-1]["snippet"] += data


def _format_results(query: str, results: list[dict], via: str) -> str:
    lines = [f'Search results for "{query}":', ""]
    for i, x in enumerate(results[:8], 1):
        lines.append(f"[{i}] {x['title'].strip()}")
        lines.append(f"    {x['url']}")
        snippet = " ".join((x.get("snippet") or "").split())
        if snippet:
            lines.append(f"    {snippet[:250]}")
    lines.append("")
    lines.append("Use fetch on the most promising URLs for details. "
                 "Prefer official sources; cite URLs you used.")
    return "\n".join(lines)


def web_search(query: str) -> str:
    """Web search: stealth real-browser engines first (DDG->Bing->Brave),
    plain httpx DuckDuckGo as fallback."""
    query = " ".join(query.split())
    if not query:
        return "Error: search query is empty."
    if len(query) > 500:
        return "Error: search query is too long (500 character limit)."
    from .. import browser
    if browser.available():
        try:
            return _format_results(query, browser.search(query), "browser")
        except Exception:
            pass  # fall through to the httpx path
    return _direct_search(query)


def _direct_search(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    endpoints = [
        f"https://html.duckduckgo.com/html/?q={q}",
        f"https://lite.duckduckgo.com/lite/?q={q}",
    ]
    last_err = "no results"
    for url in endpoints:
        try:
            r = httpx.get(url, headers=UA, timeout=20.0, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as e:
            last_err = str(e)
            continue
        if re.search(r"unusual traffic|captcha|challenge-form", r.text, re.I):
            last_err = "search endpoint rate-limited; wait a minute and retry"
            continue
        parser = _DDGResults()
        try:
            parser.feed(r.text)
        except Exception:
            pass
        results = [x for x in parser.results if x["title"].strip()][:8]
        if results:
            return _format_results(query, results, "direct")
    return f"Error: search failed ({last_err}). Try different words or fetch a site directly."


def _jina_reader(url: str) -> str | None:
    """Keyless fallback reader that renders JS-heavy pages to markdown."""
    try:
        r = httpx.get(f"https://r.jina.ai/{url}", timeout=40.0,
                      headers={**UA, "X-Return-Format": "markdown"})
        if r.status_code == 200 and len(r.text) > 80:
            text = r.text
            ci = text.find("Markdown Content:")
            if ci != -1:
                text = text[ci + len("Markdown Content:"):]
            return text.strip()
    except httpx.HTTPError:
        pass
    return None


def fetch_url(url: str) -> str:
    url = url.strip()
    if not url:
        return "Error: URL is empty."
    if len(url) > 4096:
        return "Error: URL is too long."
    if not re.match(r"^https?://", url):
        url = "https://" + url
    try:
        url = _validate_public_url(url)
    except ValueError as e:
        return f"Error fetching {url}: {e}. Use the run tool for an explicitly requested local URL."
    # real browser first: JS sites render, Reddit gets the rich .json path
    from .. import browser
    if browser.available():
        try:
            text = browser.fetch(url)
            if text and len(text.strip()) > 80:
                if len(text) > MAX_TEXT:
                    text = text[:MAX_TEXT] + "\n...[truncated]"
                return text
        except Exception:
            pass  # fall through to the httpx path
    try:
        r = _get_with_safe_redirects(url, timeout=30.0, headers=UA)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fallback = _jina_reader(url)
        if fallback:
            return fallback[:MAX_TEXT] + ("\n...[truncated]" if len(fallback) > MAX_TEXT else "")
        return f"Error fetching {url}: {e}"
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype and "json" not in ctype:
        return f"Error: content-type '{ctype}' is not text. Not fetched."
    if "html" in ctype:
        parser = _TextExtractor()
        try:
            parser.feed(r.text)
        except Exception:
            pass
        text = re.sub(r"\n{3,}", "\n\n", " ".join(parser.parts)
                      .replace(" \n ", "\n").replace("\n ", "\n"))
        text = "\n".join(line.strip() for line in text.splitlines())
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        title = parser.title.strip()
        body = (f"# {title}\n\n" if title else "") + text
        # JS-heavy page with no real content? Try the reader service.
        if len(text) < 200:
            alt = _jina_reader(url)
            if alt and len(alt) > len(text):
                body = alt
    else:
        body = r.text
    if len(body) > MAX_TEXT:
        body = body[:MAX_TEXT] + f"\n...[truncated, page is {len(r.text):,} chars]"
    return body or "(no readable text found)"
