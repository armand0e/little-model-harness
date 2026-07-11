"""Persistent memory + cross-session recall (Hermes-style learning loop).

- memory.md: agent-curated durable facts, injected into every system prompt
  (volatile tier). The model writes to it with the remember tool.
- search_sessions: lets the model find how PAST sessions solved something,
  without carrying those transcripts in context.
"""
from __future__ import annotations

import datetime
import json
import re

from .config import MEMORY_FILE, SESSIONS_DIR

MEMORY_MAX_LINES = 120        # oldest facts fall off
MEMORY_INJECT_CHARS = 1500    # cap what goes into the system prompt


def remember(fact: str) -> str:
    fact = " ".join(fact.split())
    if not fact:
        return "Error: empty fact."
    if len(fact) > 300:
        return "Error: keep memories under 300 characters — save one fact at a time."
    lines = []
    if MEMORY_FILE.exists():
        lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    stamp = datetime.date.today().isoformat()
    lines.append(f"- [{stamp}] {fact}")
    if len(lines) > MEMORY_MAX_LINES:
        lines = lines[-MEMORY_MAX_LINES:]
    MEMORY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Remembered. ({len(lines)} memories stored)"


def load_memory() -> str:
    """Tail of memory.md, capped for prompt injection."""
    if not MEMORY_FILE.exists():
        return ""
    text = MEMORY_FILE.read_text(encoding="utf-8").strip()
    if len(text) > MEMORY_INJECT_CHARS:
        text = "…\n" + text[-MEMORY_INJECT_CHARS:]
    return text


def memory_text() -> str:
    return MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else ""


# ---------- cross-session search ----------
def _tokenize(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", s.lower())}


def search_sessions(query: str) -> str:
    terms = _tokenize(query)
    if not terms:
        return "Error: give a few keywords to search for."
    hits = []
    for path in (SESSIONS_DIR.glob("*.json") if SESSIONS_DIR.is_dir() else []):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        title = data.get("title", "")
        when = datetime.datetime.fromtimestamp(
            data.get("updated", 0)).strftime("%Y-%m-%d")
        best_score, best_snip = 0, ""
        for item in data.get("display", []):
            text = item.get("text") or item.get("result") or ""
            if not isinstance(text, str) or len(text) < 10:
                continue
            score = len(terms & _tokenize(text))
            if score > best_score:
                best_score = score
                # window around the first matching term
                low = text.lower()
                pos = min((low.find(t) for t in terms if low.find(t) >= 0),
                          default=0)
                start = max(0, pos - 80)
                best_snip = " ".join(text[start:start + 300].split())
        title_score = len(terms & _tokenize(title))
        if best_score + title_score > 0:
            hits.append((best_score + title_score * 2, when, title, best_snip))
    if not hits:
        return "No past sessions matched. Try different keywords."
    hits.sort(reverse=True)
    out = [f"Past sessions matching '{query}':"]
    for _, when, title, snip in hits[:5]:
        out.append(f"- [{when}] {title[:70]}")
        if snip:
            out.append(f"    …{snip}…")
    return "\n".join(out)
