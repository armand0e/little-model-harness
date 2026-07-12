"""Token estimation.

We don't have a tokenizer for arbitrary local models, so we estimate
(~4 chars/token for English/code) and continuously calibrate against the
exact `usage.prompt_tokens` the server reports on every response.
"""
from __future__ import annotations

import json

CHARS_PER_TOKEN = 4.0
NON_ASCII_CHARS_PER_TOKEN = 1.0
MSG_OVERHEAD = 8  # per-message chat-template overhead


def estimate_text(text: str) -> int:
    if not text:
        return 0
    # A single global chars/token ratio badly undercounts CJK, emoji, and many
    # mixed-language prompts before endpoint usage can calibrate us. Treat
    # non-ASCII code points conservatively; the live calibrator recovers any
    # model-specific overestimate after the first response.
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = sum(2 if ord(char) > 0xFFFF else 1
                          for char in text if ord(char) >= 128)
    return max(1, int(ascii_chars / CHARS_PER_TOKEN
                      + non_ascii_chars / NON_ASCII_CHARS_PER_TOKEN))


IMAGE_TOKENS = 800  # rough per-image cost; base64 length is NOT the cost


def estimate_message(msg: dict) -> int:
    if not isinstance(msg, dict):
        return MSG_OVERHEAD
    n = MSG_OVERHEAD
    content = msg.get("content") or ""
    if isinstance(content, str):
        n += estimate_text(content)
    elif isinstance(content, list):  # multimodal: text parts + images
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                n += estimate_text(str(part.get("text", "")))
            elif part.get("type") == "image_url":
                n += IMAGE_TOKENS
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function", {})
        if not isinstance(fn, dict):
            continue
        n += (estimate_text(str(fn.get("name", "")))
              + estimate_text(str(fn.get("arguments", ""))) + 10)
    return n


def estimate_messages(messages: list[dict]) -> int:
    return sum(estimate_message(m) for m in messages)


def estimate_tools(tools: list[dict]) -> int:
    if not tools:
        return 0
    return estimate_text(json.dumps(tools))


class Calibrator:
    """Tracks the ratio between our estimates and the server's real counts."""

    def __init__(self) -> None:
        self.ratio = 1.0
        self.last_real_prompt = 0

    def update(self, estimated: int, real_prompt_tokens: int) -> None:
        if estimated > 0 and real_prompt_tokens > 0:
            observed = real_prompt_tokens / estimated
            # Exponential moving average, clamped to sane bounds.
            self.ratio = min(2.5, max(0.5, 0.7 * self.ratio + 0.3 * observed))
            self.last_real_prompt = real_prompt_tokens

    def corrected(self, estimated: int) -> int:
        return int(estimated * self.ratio)
