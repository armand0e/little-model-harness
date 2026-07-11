"""Terminal UI. Run with: python -m harness.tui"""
from __future__ import annotations

import json
import sys

# Windows consoles often default to cp1252, which can't print the glyphs
# rich uses. Force UTF-8 before rich binds to stdout.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from .agent import Agent

console = Console()

HELP = """\
Commands:
  /help      show this help
  /new       start a fresh conversation
  /skills    list available skills and which are loaded
  /context   show token usage and context status
  /quit      exit
Anything else is sent to the agent."""


def _fmt_args(arguments: str) -> str:
    try:
        args = json.loads(arguments)
        parts = []
        for k, v in args.items():
            s = str(v).replace("\n", " ")
            parts.append(f"{k}={s[:80]}{'…' if len(s) > 80 else ''}")
        return ", ".join(parts)
    except Exception:
        return arguments[:120]


class TuiRenderer:
    """Streams reasoning dimly, buffers content for markdown rendering."""

    def __init__(self) -> None:
        self.content_buf = ""
        self.reasoning_open = False
        self.reasoning_chars = 0

    def __call__(self, etype: str, data) -> None:
        if etype == "reasoning_delta":
            if not self.reasoning_open:
                console.print(Text("thinking… ", style="dim italic"), end="")
                self.reasoning_open = True
            self.reasoning_chars += len(data)
            # A live dot per ~80 chars keeps the user informed w/o spam.
            if self.reasoning_chars // 80 > (self.reasoning_chars - len(data)) // 80:
                console.print(Text(".", style="dim"), end="")
        elif etype == "content_delta":
            self._end_reasoning()
            self.content_buf += data
        elif etype == "tool_call":
            self._end_reasoning()
            self._flush_content()
            console.print(Text(f"  ⚙ {data['name']}({_fmt_args(data['arguments'])})",
                               style="cyan"))
        elif etype == "tool_result":
            preview = (data["result"] or "").strip().splitlines()
            head = preview[0][:100] if preview else "(empty)"
            more = f" (+{len(preview) - 1} lines)" if len(preview) > 1 else ""
            style = "red" if head.startswith("Error") else "dim"
            console.print(Text(f"    → {head}{more}", style=style))
        elif etype == "context":
            console.print(Text(f"  [context] {data}", style="yellow dim"))
        elif etype == "error":
            self._end_reasoning()
            console.print(Text(f"  ✗ {data}", style="bold red"))

    def _end_reasoning(self) -> None:
        if self.reasoning_open:
            console.print()
            self.reasoning_open = False
            self.reasoning_chars = 0

    def _flush_content(self) -> None:
        if self.content_buf.strip():
            console.print(Text(self.content_buf.strip(), style="white"))
        self.content_buf = ""

    def finish(self, final_text: str) -> None:
        self._end_reasoning()
        self.content_buf = ""
        if final_text.strip():
            console.print(Markdown(final_text.strip()))


def show_context(agent: Agent) -> None:
    st = agent.context_status()
    pct = 100 * st["estimated_tokens"] / st["window"]
    console.print(Panel(
        f"estimated context: [bold]{st['estimated_tokens']:,}[/] / {st['window']:,} tokens ({pct:.0f}%)\n"
        f"last real prompt:  {st['last_prompt_tokens']:,} tokens\n"
        f"compaction at:     {st['compact_threshold']:,} tokens "
        f"(compacted {st['compactions']}x so far)\n"
        f"skills loaded:     {', '.join(st['skills_loaded']) or 'none'}",
        title="context", border_style="blue"))


def main() -> None:
    agent = Agent()
    console.print(Panel(
        f"[bold]Little Model Harness[/] — agent for small local LLMs\n"
        f"model: {agent.cfg.model} @ {agent.cfg.base_url}\n"
        f"workspace: {agent.workspace}\n"
        f"skills: {', '.join(agent.skills.skills) or 'none'}   [dim](/help for commands)[/]",
        border_style="green"))

    while True:
        try:
            user = console.input("\n[bold green]you ›[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nbye")
            return
        if not user:
            continue
        if user in ("/quit", "/exit", "/q"):
            return
        if user == "/help":
            console.print(HELP)
            continue
        if user == "/new":
            agent.reset()
            console.print("[yellow]started a fresh conversation[/]")
            continue
        if user == "/skills":
            for name, s in agent.skills.skills.items():
                mark = "[green]●[/]" if name in agent.skills.loaded else "[dim]○[/]"
                console.print(f" {mark} [bold]{name}[/] — {s.description}")
            continue
        if user == "/context":
            show_context(agent)
            continue

        console.print(Rule(style="dim"))
        renderer = TuiRenderer()
        try:
            final = agent.run_turn(user, on_event=renderer)
        except KeyboardInterrupt:
            renderer._end_reasoning()
            console.print("[red]interrupted[/]")
            continue
        renderer.finish(final)
        st = agent.context_status()
        console.print(Text(
            f"[{st['estimated_tokens']:,}/{st['window']:,} tokens]",
            style="dim"), justify="right")


if __name__ == "__main__":
    main()
