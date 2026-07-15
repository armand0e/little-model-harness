"""Deep research mode.

A structured multi-phase pipeline that turns one request into a cited
research report, comparable to hosted "deep research" agents but driven
deterministically in Python so it stays reliable on small local models:

  scope      one model call decides: clarify, answer from the previous
             report, or research (returns a brief + sub-questions + queries)
  rounds     search -> triage (model picks URLs) -> fetch -> extract notes
  reflect    after each round the model closes gaps with new queries or stops
  synthesize stream a markdown report with inline [n] citations; a Sources
             section is appended deterministically and the report is saved
             to the workspace

Every model call is standalone (bounded prompt, no shared context), so the
pipeline works on 8k windows and scales its budgets up on larger ones. All
progress is emitted through the existing agent event vocabulary
(activity/tool_call/tool_result/content_delta/context), so jobs, persistence,
and every client render it without changes.
"""
from __future__ import annotations

import datetime
import json
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .tools.web import fetch_url, search_results

MAX_CLARIFY_QUESTIONS = 3
TOOL_EVENT_PREVIEW_CHARS = 1500
NOTE_CHARS = 300
# Approximate chars per token used to bound prompt text for a given window.
CHARS_PER_TOKEN = 3


class ResearchStopped(Exception):
    """Raised when the user hits stop mid-pipeline."""


@dataclass
class Source:
    sid: int
    url: str
    title: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Budget:
    rounds: int
    queries_per_round: int
    fetches_per_round: int
    max_sources: int
    notes_per_source: int
    report_tokens: int

    @classmethod
    def for_config(cls, cfg) -> "Budget":
        window = cfg.context_window
        rounds = max(1, min(6, getattr(cfg, "research_max_rounds", 3)))
        max_sources = max(3, min(24, getattr(cfg, "research_max_sources", 12)))
        if window <= 8192:
            return cls(min(rounds, 2), 2, 3, min(max_sources, 6), 4,
                       min(cfg.max_output_tokens, 1600))
        if window <= 16384:
            return cls(min(rounds, 3), 3, 4, min(max_sources, 9), 6,
                       min(cfg.max_output_tokens, 2600))
        return cls(rounds, 4, 5, max_sources, 8,
                   min(cfg.max_output_tokens, max(2048, window // 8)))


def parse_json_object(text: str) -> dict | None:
    """Extract the first JSON object from model output, tolerating fences,
    surrounding prose, and trailing commas."""
    if not text:
        return None
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate,
                       flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = candidate[start:end + 1]
    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            value = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _string_list(value, limit: int, max_chars: int = 400) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(" ".join(item.split())[:max_chars])
        if len(out) >= limit:
            break
    return out


def _clip(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


class _Pipeline:
    def __init__(self, agent, emit: Callable[[str, object], None]) -> None:
        self.agent = agent
        self.cfg = agent.cfg
        self.emit = emit
        self.budget = Budget.for_config(agent.cfg)
        self.sources: list[Source] = []
        self.seen_urls: set[str] = set()
        self.used_queries: list[str] = []
        self.brief = ""
        self.sub_questions: list[str] = []
        self.searches_run = 0
        self.started = time.monotonic()

    # ---- plumbing ----
    def _check_stop(self) -> None:
        if self.agent._stop.is_set():
            raise ResearchStopped()

    def _interruptible(self, fn: Callable, *args):
        """Run a blocking network helper while staying stop-responsive."""
        result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                result.put((True, fn(*args)))
            except BaseException as exc:
                result.put((False, exc))

        threading.Thread(target=worker, name="lmh-research-network",
                         daemon=True).start()
        while True:
            self._check_stop()
            try:
                ok, value = result.get(timeout=0.1)
            except queue.Empty:
                continue
            if ok:
                return value
            if isinstance(value, BaseException):
                raise value
            raise RuntimeError(str(value))

    def _drain_steers(self) -> None:
        with self.agent._steer_lock:
            updates = list(self.agent._steering)
            self.agent._steering.clear()
        for text in updates:
            self.emit("steer_applied", text)
            self.brief += "\nUser update (mid-research): " + _clip(text, 600)

    def _call(self, system: str, user: str, max_tokens: int,
              stream_content: bool = False, temperature: float = 0.2):
        """One bounded, standalone model call. Streams internally so the
        stop button interrupts between tokens; optionally forwards content
        deltas to the client."""
        self._check_stop()
        prompt_budget_chars = max(
            2000,
            (self.cfg.context_window - max_tokens - 800) * CHARS_PER_TOKEN)
        if len(system) + len(user) > prompt_budget_chars:
            user = _clip(user, max(1000, prompt_budget_chars - len(system)))

        def on_delta(kind: str, text: str) -> None:
            self._check_stop()
            if stream_content and kind == "content":
                self.emit("content_delta", text)

        try:
            return self.agent.llm.chat(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=temperature, max_tokens=max_tokens,
                on_delta=on_delta)
        except RuntimeError:
            self._check_stop()
            raise

    def _call_json(self, system: str, user: str, max_tokens: int) -> dict | None:
        try:
            resp = self._call(system, user, max_tokens)
        except ResearchStopped:
            raise
        except Exception as exc:
            self.emit("context", f"Research step degraded ({exc}); continuing "
                                 "with a fallback.")
            return None
        return (parse_json_object(resp.content)
                or parse_json_object(resp.reasoning))

    def _tool_event(self, name: str, arguments: dict, result: str) -> None:
        """Show a finished search/fetch as a normal tool card."""
        self.emit("tool_call", {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False)})
        self.emit("tool_result", {
            "name": name, "result": _clip(result, TOOL_EVENT_PREVIEW_CHARS)})

    # ---- phase: scope ----
    def _history(self) -> tuple[str, bool]:
        """Compact tail of this conversation (excluding the current request)."""
        parts: list[str] = []
        has_history = False
        for message in self.agent.ctx.messages[-7:-1]:
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            if not content.strip():
                continue
            has_history = True
            limit = 2600 if role == "assistant" else 700
            parts.append(f"{role}: {_clip(content.strip(), limit)}")
        return "\n".join(parts[-4:]), has_history

    def scope(self, user_text: str) -> dict:
        history, has_history = self._history()
        self.emit("activity", {"phase": "research_scoping"})
        system = (
            "You scope requests for a deep-research agent. Reply with ONE "
            "JSON object only, no prose. Choose exactly one action:\n"
            '{"action":"clarify","questions":["…"]} — only if the request is '
            "genuinely too ambiguous to research well (unknown subject, "
            "purpose, or scope). Max 3 short questions. Never clarify when a "
            "reasonable default scope exists.\n"
            '{"action":"answer"} — only if there is a previous report in the '
            "conversation and the new message is a quick question about it "
            "(no new information needed).\n"
            '{"action":"research","brief":"one-paragraph research brief",'
            '"sub_questions":["…"],"queries":["…"]} — otherwise. 3-5 '
            "sub_questions covering distinct angles; 2-4 diverse, specific "
            "web search queries (each under 10 words).")
        user = (f"Today: {datetime.date.today().isoformat()}\n"
                + (f"Conversation so far:\n{history}\n\n" if history else "")
                + f"New request:\n{user_text}")
        data = self._call_json(system, user, max_tokens=1000) or {}
        action = data.get("action")
        if action == "clarify" and not has_history:
            questions = _string_list(
                data.get("questions"), MAX_CLARIFY_QUESTIONS)
            if questions:
                return {"action": "clarify", "questions": questions}
        if action == "answer" and has_history:
            return {"action": "answer"}
        brief = data.get("brief")
        if not isinstance(brief, str) or not brief.strip():
            brief = user_text.strip()
        queries = _string_list(data.get("queries"),
                               self.budget.queries_per_round, 80)
        if not queries:
            queries = [" ".join(user_text.split()[:10])]
        return {
            "action": "research",
            "brief": _clip(" ".join(brief.split()), 1200),
            "sub_questions": _string_list(data.get("sub_questions"), 5, 200),
            "queries": queries,
        }

    # ---- phase: search + read rounds ----
    def _search(self, query: str) -> list[dict]:
        self._check_stop()
        query = " ".join(query.split())[:200]
        if not query or query.casefold() in (
                q.casefold() for q in self.used_queries):
            return []
        self.used_queries.append(query)
        self.searches_run += 1
        results, error = self._interruptible(search_results, query)
        if results:
            display = "\n".join(
                f"[{i}] {r.get('title', '').strip()}\n    {r.get('url', '')}"
                + (f"\n    {_clip(' '.join((r.get('snippet') or '').split()), 200)}"
                   if r.get("snippet") else "")
                for i, r in enumerate(results, 1))
        else:
            display = f"Error: search failed ({error})."
        self._tool_event("web_search", {"query": query}, display)
        return results

    def _triage(self, candidates: list[dict]) -> list[str]:
        """Ask the model which results to read; fall back to top hits."""
        fresh = [c for c in candidates
                 if c.get("url", "").startswith("http")
                 and c["url"] not in self.seen_urls]
        deduped: list[dict] = []
        for c in fresh:
            if c["url"] not in {d["url"] for d in deduped}:
                deduped.append(c)
        if not deduped:
            return []
        limit = self.budget.fetches_per_round
        if len(deduped) <= limit:
            return [c["url"] for c in deduped]
        listing = "\n".join(
            f"{i}. {_clip(c.get('title', ''), 120)} — {c['url']}\n"
            f"   {_clip(' '.join((c.get('snippet') or '').split()), 180)}"
            for i, c in enumerate(deduped[:24], 1))
        system = (
            "You pick which search results a research agent should read. "
            "Prefer primary/official sources, recognized publications, and "
            "coverage of different sub-questions over near-duplicates. Reply "
            'with ONE JSON object only: {"read":[1,4,…]} using at most '
            f"{limit} numbers from the list.")
        user = (f"Research brief: {self.brief}\n"
                + (f"Sub-questions: {'; '.join(self.sub_questions)}\n"
                   if self.sub_questions else "")
                + f"\nCandidates:\n{listing}")
        data = self._call_json(system, user, max_tokens=600) or {}
        picks: list[str] = []
        raw = data.get("read")
        if isinstance(raw, list):
            for item in raw:
                try:
                    index = int(item)
                except (TypeError, ValueError):
                    continue
                if 1 <= index <= len(deduped[:24]):
                    url = deduped[index - 1]["url"]
                    if url not in picks:
                        picks.append(url)
                if len(picks) >= limit:
                    break
        return picks or [c["url"] for c in deduped[:limit]]

    def _read_source(self, url: str) -> None:
        self._check_stop()
        self.seen_urls.add(url)
        self.emit("activity", {"phase": "research_reading",
                               "url": _clip(url, 120)})
        text = self._interruptible(fetch_url, url)
        self._tool_event("fetch", {"url": url}, text)
        if text.lstrip().startswith("Error") or len(text.strip()) < 120:
            return
        title_match = re.match(r"^#\s+(.+)", text)
        fallback_title = (title_match.group(1).strip() if title_match
                          else url.split("//", 1)[-1][:80])
        system = (
            "You extract facts from one web page for a research brief. Reply "
            "with ONE JSON object only:\n"
            '{"relevant":true,"title":"short page title","notes":["…"]}\n'
            f"notes: at most {self.budget.notes_per_source} findings that "
            "bear on the brief — each a single self-contained sentence with "
            "concrete names, numbers, and dates from the page. Never invent "
            'facts. If the page does not help, reply {"relevant":false}.')
        user = (f"Research brief: {self.brief}\n"
                + (f"Sub-questions: {'; '.join(self.sub_questions)}\n"
                   if self.sub_questions else "")
                + f"\nPage URL: {url}\nPage content:\n{text}")
        data = self._call_json(system, user, max_tokens=1000)
        if data is None or data.get("relevant") is False:
            return
        notes = _string_list(data.get("notes"),
                             self.budget.notes_per_source, NOTE_CHARS)
        if not notes:
            return
        title = data.get("title")
        if not isinstance(title, str) or not title.strip():
            title = fallback_title
        self.sources.append(Source(
            sid=len(self.sources) + 1, url=url,
            title=" ".join(title.split())[:120], notes=notes))

    def _reflect(self) -> list[str]:
        """Decide whether coverage is sufficient; if not, return new queries."""
        self.emit("activity", {"phase": "research_reviewing"})
        digest = "\n".join(
            f"[{s.sid}] {s.title}\n" + "\n".join(f"  - {n}" for n in s.notes)
            for s in self.sources)
        system = (
            "You review research coverage. Reply with ONE JSON object only:\n"
            '{"complete":true} when the notes can support a thorough report, '
            'or {"complete":false,"queries":["…"]} with 1-'
            f"{self.budget.queries_per_round} NEW web searches (under 10 "
            "words each, different from those already run) that target the "
            "most important remaining gaps.")
        user = (f"Research brief: {self.brief}\n"
                + (f"Sub-questions: {'; '.join(self.sub_questions)}\n"
                   if self.sub_questions else "")
                + f"Searches already run: {'; '.join(self.used_queries)}\n"
                + f"\nNotes so far:\n{_clip(digest, 14000)}")
        data = self._call_json(system, user, max_tokens=700)
        if not data or data.get("complete") is not False:
            return []
        used = {q.casefold() for q in self.used_queries}
        return [q for q in _string_list(data.get("queries"),
                                        self.budget.queries_per_round, 80)
                if q.casefold() not in used]

    def research(self, plan: dict) -> None:
        self.brief = plan["brief"]
        self.sub_questions = plan["sub_questions"]
        plan_lines = ["Deep research plan", f"Goal: {self.brief}"]
        if self.sub_questions:
            plan_lines += ["Angles:"] + [f"- {q}" for q in self.sub_questions]
        plan_lines.append("Initial searches: " + "; ".join(plan["queries"]))
        self.emit("context", "\n".join(plan_lines))
        queries = plan["queries"]
        for round_no in range(1, self.budget.rounds + 1):
            self._drain_steers()
            self.emit("activity", {"phase": "research_searching",
                                   "round": round_no,
                                   "rounds": self.budget.rounds})
            candidates: list[dict] = []
            for query in queries[:self.budget.queries_per_round]:
                candidates.extend(self._search(query))
            for url in self._triage(candidates):
                if len(self.sources) >= self.budget.max_sources:
                    break
                self._read_source(url)
            if len(self.sources) >= self.budget.max_sources:
                break
            if round_no >= self.budget.rounds or not self.sources:
                break
            queries = self._reflect()
            if not queries:
                break

    # ---- phase: synthesize ----
    def _notes_digest(self, char_budget: int) -> str:
        blocks = [
            f"[{s.sid}] {s.title} — {s.url}\n"
            + "\n".join(f"  - {n}" for n in s.notes)
            for s in self.sources]
        digest = "\n".join(blocks)
        while len(digest) > char_budget and any(
                len(s.notes) > 2 for s in self.sources):
            for s in self.sources:
                if len(s.notes) > 2:
                    s.notes.pop()
            blocks = [
                f"[{s.sid}] {s.title} — {s.url}\n"
                + "\n".join(f"  - {n}" for n in s.notes)
                for s in self.sources]
            digest = "\n".join(blocks)
        return _clip(digest, char_budget)

    def synthesize(self, user_text: str) -> str:
        self._drain_steers()
        self.emit("activity", {"phase": "research_writing"})
        report_tokens = self.budget.report_tokens
        digest_budget = max(
            4000,
            (self.cfg.context_window - report_tokens - 1500) * CHARS_PER_TOKEN)
        digest = self._notes_digest(min(digest_budget, 60_000))
        system = (
            "You are an expert analyst writing a deep-research report in "
            "markdown from the numbered source notes provided. Requirements:\n"
            "- Start with a # title, then an '## Executive summary' of 3-6 "
            "sentences with the key conclusions.\n"
            "- Organize the body into thematic ## sections answering the "
            "brief; use tables when comparing options or figures.\n"
            "- Put an inline citation like [2] (or [1][3]) immediately after "
            "every claim it supports; every source note you use must be "
            "cited by its number.\n"
            "- Use ONLY the provided notes — no outside knowledge, no "
            "invented sources or numbers. Point out where sources conflict.\n"
            "- End with a short '## Remaining gaps' section if material "
            "questions are still open.\n"
            "- Do NOT write a Sources/References section; it is appended "
            "automatically.")
        user = (f"Today: {datetime.date.today().isoformat()}\n"
                f"Research brief: {self.brief}\n"
                + (f"Sub-questions: {'; '.join(self.sub_questions)}\n"
                   if self.sub_questions else "")
                + f"Original request: {_clip(user_text, 1500)}\n"
                + f"\nSource notes:\n{digest}")
        resp = self._call(system, user, max_tokens=report_tokens,
                          stream_content=True, temperature=0.3)
        report = resp.content.strip()
        if resp.finish_reason == "length" and report:
            continuation = self._call(
                system,
                user + "\n\nYour draft was cut off. Continue EXACTLY where "
                "this ends, without repeating anything:\n…"
                + report[-1200:],
                max_tokens=report_tokens, stream_content=True,
                temperature=0.3)
            report = report.rstrip() + continuation.content
        return report.strip()

    def sources_section(self, report: str) -> str:
        cited = {int(m) for m in re.findall(r"\[(\d+)\]", report)}
        listed = [s for s in self.sources if s.sid in cited] or self.sources
        lines = ["", "## Sources", ""]
        lines += [f"[{s.sid}] {s.title} — {s.url}" for s in listed]
        return "\n".join(lines)


def _save_report(agent, report: str) -> str:
    """Write the report to the workspace; return a one-line footer."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = agent.workspace / f"research-report-{stamp}.md"
    try:
        agent.workspace.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
    except OSError as exc:
        return f"\n\n_Could not save the report file: {exc}_"
    return f"\n\n_Report saved to {path.name} in the workspace._"


def run_research(agent, user_text: str,
                 on_event: Optional[Callable[[str, object], None]] = None) -> str:
    """Run one deep-research turn. Mirrors Agent.run_turn's contract:
    appends the user/assistant exchange to the context, emits progress
    events, honors stop and steering, and returns the final text."""
    emit = on_event or (lambda t, d: None)
    reset_transport = getattr(agent.llm, "reset_cancel", None)
    if not agent._stop.is_set() and callable(reset_transport):
        reset_transport()
    agent.turn_no += 1
    agent.turn_marks.append({"turn": agent.turn_no,
                             "msg_index": len(agent.ctx.messages)})
    agent.ctx.add_user(user_text)
    with agent._steer_lock:
        agent._steering.clear()
        agent._accepting_steer = True
    pipeline = _Pipeline(agent, emit)
    final = ""
    try:
        plan = pipeline.scope(user_text)
        if plan["action"] == "clarify":
            questions = "\n".join(
                f"{i}. {q}" for i, q in enumerate(plan["questions"], 1))
            final = ("Before I start the deep research, a few quick "
                     f"questions:\n\n{questions}\n\nAnswer whichever apply — "
                     "or say “just proceed” and I'll use sensible defaults.")
            emit("content_delta", final)
        elif plan["action"] == "answer":
            resp = pipeline._call(
                "Answer the user's question using ONLY the conversation "
                "excerpt from your earlier research report. Keep existing "
                "[n] citation markers on the claims they support. If the "
                "answer is not in the report, say so and offer to research "
                "it.",
                "Conversation excerpt:\n" + pipeline._history()[0]
                + f"\n\nQuestion: {user_text}",
                max_tokens=min(agent.cfg.max_output_tokens, 1500),
                stream_content=True, temperature=0.3)
            final = resp.content.strip() or "(no answer produced)"
        else:
            pipeline.research(plan)
            if not pipeline.sources:
                final = (
                    "I could not gather usable sources for this request. "
                    "Searches tried: "
                    + ("; ".join(pipeline.used_queries) or "(none)")
                    + ". The web may be unreachable from this machine, or "
                    "the topic may need different wording — try rephrasing "
                    "or narrowing the request.")
                emit("content_delta", final)
            else:
                report = pipeline.synthesize(user_text)
                sources = pipeline.sources_section(report)
                final = report + "\n" + sources
                footer = _save_report(agent, final)
                emit("content_delta", "\n" + sources + footer)
                final += footer
                agent._research_sources = [
                    {"sid": s.sid, "url": s.url, "title": s.title}
                    for s in pipeline.sources]
    except ResearchStopped:
        final = "(stopped by user)"
    except Exception as exc:
        if agent._stop.is_set():
            final = "(stopped by user)"
        else:
            emit("error", f"Deep research failed: {type(exc).__name__}: {exc}")
            final = (f"Deep research failed ({type(exc).__name__}: {exc}). "
                     "Progress so far is shown above; send the request again "
                     "to retry.")
    finally:
        with agent._steer_lock:
            agent._accepting_steer = False
            agent._steering.clear()
        agent._stop.clear()
        if callable(reset_transport):
            reset_transport()
    agent.ctx.add_assistant({"role": "assistant", "content": final})
    return final
