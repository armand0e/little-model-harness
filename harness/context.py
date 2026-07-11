"""Context management: keep the whole conversation inside a 32k window.

Three layers of defense, applied in order when the budget is exceeded:
1. Per-result caps — every tool result is truncated at insertion time.
2. Fading — tool results older than the last N user turns collapse to a stub.
3. Compaction — the model itself summarizes the older half of the
   conversation into one message; recent turns are kept verbatim.
"""
from __future__ import annotations

from typing import Callable, Optional

from .config import Config
from .llm import LLMClient
from .tokens import Calibrator, estimate_message, estimate_messages, estimate_text

FADE_STUB = "[old tool result removed to save space — re-run the tool if needed]"

COMPACT_PROMPT = (
    "Summarize the conversation so far for your own memory. Keep it under "
    "300 words. Include: the user's goal, what has been done (files "
    "created/edited with paths, commands run, skills loaded), key facts "
    "discovered, and what remains to do. Output only the summary."
)


class ContextManager:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.messages: list[dict] = []
        self.calibrator = Calibrator()
        self.compactions = 0

    # ---- building ----
    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, msg: dict) -> None:
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        # On small windows a 6k-char tool result would drown the model —
        # scale the cap so one result never exceeds ~1/8 of the window.
        cap = min(self.cfg.tool_result_max_chars,
                  max(1200, (self.cfg.context_window // 8) * 4))
        if len(result) > cap:
            result = (result[:cap // 2]
                      + "\n...[result truncated to fit context]...\n"
                      + result[-cap // 2:])
        self.messages.append({
            "role": "tool", "tool_call_id": tool_call_id,
            "name": name, "content": result,
        })

    def reset(self) -> None:
        self.messages.clear()
        self.compactions = 0

    # ---- accounting ----
    def estimated_tokens(self, system_and_tools_tokens: int = 0) -> int:
        est = estimate_messages(self.messages) + system_and_tools_tokens
        return self.calibrator.corrected(est)

    def note_usage(self, estimated_prompt: int, real_prompt_tokens: int) -> None:
        self.calibrator.update(estimated_prompt, real_prompt_tokens)

    # ---- budget enforcement ----
    def threshold(self) -> int:
        """Compact when the conversation reaches window - output_reserve
        (16k of generation headroom by default). Small windows fall back to
        half the window so the model always keeps room to work."""
        cfg = self.cfg
        return max(1024, min(cfg.context_window - 1024,
                             max(cfg.context_window - cfg.output_reserve,
                                 cfg.context_window // 2)))

    def ensure_budget(self, llm: LLMClient, system_and_tools_tokens: int,
                      on_event: Optional[Callable] = None) -> None:
        limit = self.threshold()
        if self.estimated_tokens(system_and_tools_tokens) <= limit:
            return
        self._fade_old_tool_results()
        if self.estimated_tokens(system_and_tools_tokens) <= limit:
            if on_event:
                on_event("context", "trimmed old tool results")
            return
        self._compact(llm, on_event)

    def _fade_old_tool_results(self) -> None:
        """Collapse stale tool results to a stub. 'Old' means before the
        Nth-from-last user turn — OR, within a single long agentic turn
        (one user message, many tool calls), anything but the most recent
        few results. Without the second rule a mono-turn session would
        never fade anything."""
        user_idx = [i for i, m in enumerate(self.messages) if m["role"] == "user"]
        keep = self.cfg.tool_result_keep_turns
        cutoff = user_idx[-keep] if len(user_idx) >= keep else 0

        tool_idx = [i for i, m in enumerate(self.messages) if m["role"] == "tool"]
        if len(tool_idx) > 6:  # keep the 6 freshest results verbatim
            cutoff = max(cutoff, tool_idx[-6])

        for m in self.messages[:cutoff]:
            if m["role"] == "tool" and isinstance(m.get("content"), str) \
                    and len(m.get("content") or "") > len(FADE_STUB):
                m["content"] = FADE_STUB
            # attached images are the biggest token consumers — drop old ones
            elif m["role"] == "user" and isinstance(m.get("content"), list):
                m["content"] = "[old image attachment removed to save space — re-read the file if needed]"

    def _compact(self, llm: LLMClient, on_event: Optional[Callable] = None) -> None:
        split = self._compaction_split()
        if split <= 0:
            return
        old, recent = self.messages[:split], self.messages[split:]
        if on_event:
            on_event("context", f"compacting {len(old)} old messages...")
        transcript = _render_transcript(old)
        # The summarization request itself must fit the window.
        max_chars = self.cfg.context_window * 3
        if len(transcript) > max_chars:
            transcript = ("[...earliest part omitted...]\n"
                          + transcript[-max_chars:])
        try:
            resp = llm.chat(
                messages=[
                    {"role": "user",
                     "content": f"Conversation transcript:\n\n{transcript}\n\n{COMPACT_PROMPT}"},
                ],
                temperature=0.2, max_tokens=600,
            )
            summary = resp.content.strip() or "(summary unavailable)"
        except Exception as e:
            summary = f"(compaction failed: {e}; older messages dropped)"
        self.messages = [
            {"role": "user",
             "content": f"[Summary of the conversation so far]\n{summary}\n[End of summary. The conversation continues below.]"},
            {"role": "assistant", "content": "Understood. Continuing."},
            *recent,
        ]
        self.compactions += 1
        if on_event:
            on_event("context", "compaction complete")

    def _compaction_split(self) -> int:
        """Pick a split point: keep the most recent messages verbatim, never
        orphan a tool result from its assistant tool_calls message. Splits at
        any non-tool boundary so a single long agentic turn (one user
        message, dozens of tool rounds) can still be compacted mid-turn."""
        target_old = estimate_messages(self.messages) * 2 // 3
        acc = 0
        split = 0
        for i, m in enumerate(self.messages):
            acc += estimate_message(m)
            if i > 0 and m["role"] != "tool" and acc >= target_old:
                split = i
                break
        if not split:
            return 0
        # Keep at least the last 6 messages verbatim...
        split = min(split, max(0, len(self.messages) - 6))
        # ...but never start the kept region on an orphaned tool message.
        while split > 0 and self.messages[split]["role"] == "tool":
            split -= 1
        return split


def _render_transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m["role"]
        content = m.get("content") or ""
        if isinstance(content, list):
            content = "[image attachment]"
        content = content.strip()
        if m.get("tool_calls"):
            calls = "; ".join(
                f"{tc['function']['name']}({tc['function']['arguments'][:120]})"
                for tc in m["tool_calls"])
            content = (content + f" [called: {calls}]").strip()
        if role == "tool":
            role = f"tool:{m.get('name', '?')}"
            content = content[:400]
        lines.append(f"{role}: {content[:800]}")
    return "\n".join(lines)
