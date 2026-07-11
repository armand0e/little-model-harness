"""The agent loop.

Events emitted to on_event(type, data):
  reasoning_delta, content_delta  — streaming text
  tool_call {name, arguments}     — model requested a tool
  tool_result {name, result}      — tool finished
  context <str>                   — trimming/compaction notices
  usage {prompt, completion}      — token usage after each model call
  error <str>
"""
from __future__ import annotations

import datetime
import json
import platform
import threading
from pathlib import Path
from typing import Callable, Optional


class TurnStopped(Exception):
    """Raised inside the streaming callback when the user hits stop."""

from .config import Config, get_default_workspace, load_config
from .context import ContextManager
from .llm import LLMClient
from .skills import SkillsManager
from .tokens import estimate_messages, estimate_text, estimate_tools
from .tools import build_registry

SYSTEM_PROMPT = """\
You are Little Harness, a capable assistant agent running on the user's \
{os_name} computer. Today is {today}. Your working directory for new files \
is: {workspace}

How to work:
- Use tools for every action. Never guess file contents or command output.
- Before a specialized task, load its skill FIRST with the skill tool, then \
follow the skill's instructions exactly. Load each skill only once. If the \
task changes domain midway (e.g. you switch tools/frameworks), load the new \
domain's skill before continuing.
- The run tool executes {shell} commands.
- Work step by step. When the task is done, stop calling tools and give the \
user a short plain-language summary (1-4 sentences) including full paths of \
any files you created.
- If a tool returns an error, read it and fix your call — don't repeat the \
same call.
- Be brief. No filler.

Method: understand the request before acting. Look at real files and real \
output instead of assuming. Act decisively; don't ask permission for obvious \
steps. Verify results against reality before claiming success. Report \
honestly, including failures.

Learning: remember(fact) stores durable facts about the user/machine for all \
future sessions. save_skill records reusable know-how you worked hard for \
(API gotchas, procedures). history_search finds how past sessions did \
something. subtask runs a fresh-context helper for self-contained digressions.

Skills you can load (grouped by topic):
{skills_index}
{memory_block}{project_block}"""

SUBTASK_LIMIT = 15


class Agent:
    def __init__(self, cfg: Optional[Config] = None,
                 workspace: Path | str | None = None) -> None:
        self.cfg = cfg or load_config()
        self.llm = LLMClient(self.cfg.base_url, self.cfg.model,
                             self.cfg.api_key, self.cfg.request_timeout)
        self.skills = SkillsManager()
        self.tools = build_registry(self.skills)
        self.ctx = ContextManager(self.cfg)
        # per-chat working folder; falls back to the global default
        self.workspace = Path(workspace) if workspace else get_default_workspace()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.last_usage = {"prompt": 0, "completion": 0}
        self._stop = threading.Event()
        self._vision: Optional[bool] = None
        # revert support: per-turn message marks + before-images of every
        # file the model writes or edits
        self.turn_no = 0
        self.turn_marks: list[dict] = []   # {turn, msg_index}
        self.checkpoints: list[dict] = []  # {turn, path, existed, before}

    def request_stop(self) -> None:
        self._stop.set()
        sub = getattr(self, "_active_sub", None)
        if sub is not None:
            sub.request_stop()

    # ---- checkpoints / revert ----
    SNAPSHOT_MAX = 500_000
    SNAPSHOT_KEEP = 60

    def record_file_snapshot(self, path: str) -> None:
        from .tools.files import _resolve
        p = _resolve(path, self.workspace)
        entry: dict = {"turn": self.turn_no, "path": str(p),
                       "existed": p.is_file(), "before": None}
        if entry["existed"]:
            try:
                if p.stat().st_size <= self.SNAPSHOT_MAX:
                    entry["before"] = p.read_text(encoding="utf-8",
                                                  errors="replace")
                else:
                    return  # too big to snapshot — don't pretend we can revert
            except OSError:
                return
        self.checkpoints.append(entry)
        if len(self.checkpoints) > self.SNAPSHOT_KEEP:
            self.checkpoints = self.checkpoints[-self.SNAPSHOT_KEEP:]

    def revert_to_turn(self, turn: int) -> list[str]:
        """Restore files touched in turn N and later; rewind the model
        context to just before turn N. Returns list of restored paths."""
        restored = []
        for cp in reversed([c for c in self.checkpoints if c["turn"] >= turn]):
            p = Path(cp["path"])
            try:
                if cp["existed"] and cp["before"] is not None:
                    p.write_text(cp["before"], encoding="utf-8")
                elif not cp["existed"] and p.is_file():
                    p.unlink()
                restored.append(cp["path"])
            except OSError:
                pass
        self.checkpoints = [c for c in self.checkpoints if c["turn"] < turn]
        mark = next((m for m in self.turn_marks if m["turn"] == turn), None)
        if mark is not None:
            del self.ctx.messages[min(mark["msg_index"], len(self.ctx.messages)):]
        else:
            # legacy sessions without marks: cut at the Nth real user message
            seen = 0
            for i, m in enumerate(self.ctx.messages):
                if m.get("role") == "user" and isinstance(m.get("content"), str) \
                        and not m["content"].startswith("[Summary"):
                    seen += 1
                    if seen == turn:
                        del self.ctx.messages[i:]
                        break
        self.turn_marks = [m for m in self.turn_marks if m["turn"] < turn]
        self.turn_no = turn - 1
        return restored

    # ---- vision ----
    def vision_supported(self) -> bool:
        """Probe the endpoint once with a 1x1 image; cache the answer."""
        if self._vision is None:
            probe = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                     "nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC")
            try:
                self.llm.chat(
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": "hi"},
                        {"type": "image_url", "image_url":
                            {"url": "data:image/png;base64," + probe}}]}],
                    max_tokens=1)
                self._vision = True
            except Exception:
                self._vision = False
        return self._vision

    def _encode_image(self, img) -> dict:
        import base64
        import io
        img.thumbnail((1024, 1024))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64," + b64}}

    def _resolve_image_marker(self, result: str) -> tuple[str, list[dict]]:
        """Turn __IMAGE_FILE__/__PDF_FILE__ markers from read_file into a
        text result plus image parts to attach (if the model has vision)."""
        try:
            if result.startswith("__IMAGE_FILE__:"):
                path = Path(result.split(":", 1)[1])
                if not self.vision_supported():
                    return (f"{path.name} is an image, but this model has no "
                            f"vision support and cannot view it.", [])
                from PIL import Image
                img = Image.open(path)
                w, h = img.size
                return (f"Loaded image {path.name} ({w}x{h}) — it is attached "
                        f"in the next message.", [self._encode_image(img)])
            if result.startswith("__PDF_FILE__:"):
                rest = result[len("__PDF_FILE__:"):]
                path_s, first_s, count_s = rest.rsplit(":", 2)
                path, first, count = Path(path_s), int(first_s), int(count_s)
                if not self.vision_supported():
                    return (f"{path.name} is a PDF and this model cannot view "
                            f"page images. Load the documents skill and use "
                            f"its read_pdf script for the text instead.", [])
                import fitz  # pymupdf
                from PIL import Image
                doc = fitz.open(str(path))
                n = doc.page_count
                parts = []
                last = min(n, first + count - 1)
                for pno in range(first - 1, last):
                    pix = doc[pno].get_pixmap(dpi=110)
                    img = Image.frombytes("RGB", (pix.width, pix.height),
                                          pix.samples)
                    parts.append(self._encode_image(img))
                doc.close()
                more = (f" Use start_line=<page> to view later pages."
                        if last < n else "")
                return (f"Rendered pages {first}-{last} of {n} from "
                        f"{path.name} — attached in the next message.{more}",
                        parts)
        except Exception as e:
            return (f"Error loading image content: {type(e).__name__}: {e}", [])
        return result, []

    # ---- prompt assembly ----
    def system_prompt(self) -> str:
        from .memory import load_memory
        mem = load_memory()
        memory_block = (f"\nMemory (facts you saved earlier):\n{mem}\n"
                        if mem else "")
        project_block = ""
        for fname in ("AGENTS.md", "CLAUDE.md", "HARNESS.md"):
            p = self.workspace / fname
            if p.is_file():
                txt = p.read_text(encoding="utf-8", errors="replace")[:1500]
                project_block = f"\nProject notes ({fname}):\n{txt}\n"
                break
        return SYSTEM_PROMPT.format(
            os_name=platform.system() + " " + platform.release(),
            shell="PowerShell" if platform.system() == "Windows" else "bash",
            today=datetime.date.today().isoformat(),
            workspace=self.workspace,
            skills_index=self.skills.index_text() or "(none installed)",
            memory_block=memory_block,
            project_block=project_block,
        )

    # ---- subagents ----
    def run_subtask(self, task: str) -> str:
        if getattr(self, "_is_sub", False):
            return "Error: subtasks can't spawn their own subtasks — do it directly."
        import copy
        sub_cfg = copy.copy(self.cfg)
        sub_cfg.max_iterations = SUBTASK_LIMIT
        sub = Agent(sub_cfg, workspace=self.workspace)
        sub._is_sub = True
        self._active_sub = sub
        try:
            result = sub.run_turn(
                task + "\n\n(You are a helper agent: finish the task, then "
                "reply with a complete, self-contained summary of findings/"
                "results and full paths of any files you created.)",
                stream=False)
        finally:
            self._active_sub = None
            sub.llm.close()
        return f"[subtask finished]\n{result}"

    def _overhead_tokens(self) -> int:
        return (estimate_text(self.system_prompt())
                + estimate_tools(self.tools.schemas()))

    def context_status(self) -> dict:
        est = self.ctx.estimated_tokens(self._overhead_tokens())
        return {
            "estimated_tokens": est,
            "window": self.cfg.context_window,
            "compact_threshold": self.ctx.threshold(),
            "compactions": self.ctx.compactions,
            "last_prompt_tokens": self.ctx.calibrator.last_real_prompt,
            "skills_loaded": sorted(self.skills.loaded),
        }

    def reset(self) -> None:
        self.ctx.reset()
        self.skills.reset()
        self.last_usage = {"prompt": 0, "completion": 0}

    # ---- main loop ----
    def run_turn(self, user_text: str,
                 on_event: Optional[Callable[[str, object], None]] = None,
                 stream: bool = True) -> str:
        emit = on_event or (lambda t, d: None)
        self._stop.clear()
        self.turn_no += 1
        self.turn_marks.append({"turn": self.turn_no,
                                "msg_index": len(self.ctx.messages)})
        # Hermes-style persistence nudge: if the last turn fought through
        # several tool errors, remind the model to bank what it learned.
        if getattr(self, "_pending_nudge", 0):
            user_text += ("\n\n[harness note: the previous turn hit "
                          f"{self._pending_nudge} tool errors before "
                          "succeeding. If you learned a reusable fix or "
                          "gotcha, call save_skill (or remember) with it.]")
            self._pending_nudge = 0
        self.ctx.add_user(user_text)
        final_text = ""
        consecutive_bad = 0
        turn_errors = 0

        for _ in range(self.cfg.max_iterations):
            if self._stop.is_set():
                final_text = "(stopped by user)"
                self.ctx.add_assistant({"role": "assistant", "content": final_text})
                break
            self.ctx.ensure_budget(self.llm, self._overhead_tokens(), emit)
            # compaction may shrink the message list — keep marks in range
            for m in self.turn_marks:
                m["msg_index"] = min(m["msg_index"], len(self.ctx.messages))
            messages = [{"role": "system", "content": self.system_prompt()}] \
                + self.ctx.messages
            est_prompt = estimate_messages(messages) + estimate_tools(self.tools.schemas())

            on_delta = None
            if stream:
                def on_delta(kind: str, text: str) -> None:
                    if self._stop.is_set():
                        raise TurnStopped()
                    emit("reasoning_delta" if kind == "reasoning"
                         else "content_delta", text)

            # Max output per message = the compaction threshold (compaction
            # guarantees at least that much room exists), clamped to what
            # actually fits so llama.cpp never rejects the request.
            corrected = self.ctx.calibrator.corrected(est_prompt)
            available = self.cfg.context_window - corrected - 256
            max_tokens = max(256, min(self.ctx.threshold(), available))

            try:
                resp = self.llm.chat(
                    messages=messages,
                    tools=self.tools.schemas(),
                    temperature=self.cfg.temperature,
                    max_tokens=max_tokens,
                    on_delta=on_delta,
                )
            except TurnStopped:
                final_text = "(stopped by user)"
                self.ctx.add_assistant({"role": "assistant", "content": final_text})
                break
            except Exception as e:
                emit("error", f"LLM request failed: {e}")
                return f"Error talking to the model: {e}"

            if resp.prompt_tokens:
                self.ctx.note_usage(est_prompt, resp.prompt_tokens)
                self.last_usage = {"prompt": resp.prompt_tokens,
                                   "completion": resp.completion_tokens}
                emit("usage", dict(self.last_usage))

            # Validate tool-call argument JSON BEFORE storing: llama.cpp's
            # chat template 500s forever on a history message with invalid
            # arguments (happens when generation is cut off mid-call).
            bad_calls: dict[str, str] = {}
            for tc in resp.tool_calls:
                try:
                    json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    preview = tc["function"]["arguments"][:120]
                    tc["function"]["arguments"] = "{}"
                    reason = ("the output token limit was hit mid-call"
                              if resp.finish_reason == "length"
                              else "the arguments were not valid JSON")
                    bad_calls[tc["id"]] = (
                        f"Error: this {tc['function']['name']} call was discarded — "
                        f"{reason} (started with: {preview!r}). Retry with a smaller "
                        f"call: write long content in several steps (write_file a "
                        f"first part, then edit_file to append).")
            self.ctx.add_assistant(resp.as_message())

            if not resp.tool_calls:
                final_text = resp.content.strip()
                break

            for tc in resp.tool_calls:
                name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                emit("tool_call", {"name": name, "arguments": args})
                if tc["id"] in bad_calls:
                    result = bad_calls[tc["id"]]
                else:
                    result = self.tools.execute(name, args, agent=self)
                images: list[dict] = []
                if result.startswith(("__IMAGE_FILE__:", "__PDF_FILE__:")):
                    result, images = self._resolve_image_marker(result)
                if result.lstrip().startswith("Error"):
                    turn_errors += 1
                emit("tool_result", {"name": name, "result": result})
                self.ctx.add_tool_result(tc["id"], name, result)
                if images:
                    self.ctx.messages.append({
                        "role": "user",
                        "content": [{"type": "text",
                                     "text": "[requested image(s) attached]"},
                                    *images]})

            # Bail out if the model keeps producing cut-off/invalid calls —
            # it will not succeed by repeating itself.
            if bad_calls and len(bad_calls) == len(resp.tool_calls):
                consecutive_bad += 1
                if consecutive_bad >= 2:
                    final_text = (
                        "I couldn't complete that: my tool calls keep getting cut "
                        "off by the output limit. Try asking for the content in "
                        "smaller pieces, or raise max output tokens in settings.")
                    self.ctx.add_assistant(
                        {"role": "assistant", "content": final_text})
                    break
            else:
                consecutive_bad = 0
        else:
            final_text = ("I hit the step limit for this request. Here is "
                          "where things stand: "
                          + (resp.content.strip() or "(see the actions above)"))
            self.ctx.add_assistant({"role": "assistant", "content": final_text})

        if turn_errors >= 3 and not final_text.startswith("Error"):
            self._pending_nudge = turn_errors
        if not final_text:
            final_text = "(done)"
        return final_text
