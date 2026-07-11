"""Minimal OpenAI-compatible chat client (llama.cpp / LM Studio / Ollama).

Supports streaming with incremental tool-call assembly. Reasoning models'
`reasoning_content` is surfaced separately and never stored in history.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx


@dataclass
class LLMResponse:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def as_message(self) -> dict:
        """History form of this response — reasoning is intentionally dropped."""
        msg: dict = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = "not-needed",
                 timeout: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def close(self) -> None:
        self._client.close()

    def reconfigure(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        """Point this client at a different endpoint/model at runtime."""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client.headers["Authorization"] = f"Bearer {api_key}"

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             temperature: float = 0.4, max_tokens: int = 2048,
             on_delta: Optional[Callable[[str, str], None]] = None) -> LLMResponse:
        """Send a chat completion. If on_delta is given, streams.

        on_delta(kind, text) is called with kind in {"content", "reasoning"}.
        """
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if on_delta is not None:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
            return self._chat_stream(payload, on_delta)
        return self._chat_once(payload)

    def _chat_once(self, payload: dict) -> LLMResponse:
        r = self._client.post(f"{self.base_url}/chat/completions", json=payload)
        if r.status_code >= 400:
            raise RuntimeError(_server_error(r.status_code, r.text))
        data = r.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        usage = data.get("usage") or {}
        return LLMResponse(
            content=msg.get("content") or "",
            reasoning=msg.get("reasoning_content") or "",
            tool_calls=_normalize_tool_calls(msg.get("tool_calls") or []),
            finish_reason=choice.get("finish_reason") or "",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    def _chat_stream(self, payload: dict, on_delta: Callable[[str, str], None]) -> LLMResponse:
        resp = LLMResponse()
        # tool calls arrive as indexed fragments; assemble by index
        pending: dict[int, dict] = {}
        with self._client.stream("POST", f"{self.base_url}/chat/completions",
                                 json=payload) as r:
            if r.status_code >= 400:
                r.read()
                raise RuntimeError(_server_error(r.status_code, r.text))
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                usage = data.get("usage")
                if usage:
                    resp.prompt_tokens = usage.get("prompt_tokens", resp.prompt_tokens)
                    resp.completion_tokens = usage.get("completion_tokens", resp.completion_tokens)
                choices = data.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if choice.get("finish_reason"):
                    resp.finish_reason = choice["finish_reason"]
                delta = choice.get("delta") or {}
                if delta.get("reasoning_content"):
                    resp.reasoning += delta["reasoning_content"]
                    on_delta("reasoning", delta["reasoning_content"])
                if delta.get("content"):
                    resp.content += delta["content"]
                    on_delta("content", delta["content"])
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = pending.setdefault(idx, {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
        resp.tool_calls = _normalize_tool_calls(
            [pending[i] for i in sorted(pending)])
        return resp


def _server_error(status: int, body: str) -> str:
    """Extract the model server's actual error message from a response."""
    try:
        detail = json.loads(body).get("error", {}).get("message", "")
    except (json.JSONDecodeError, AttributeError):
        detail = body[:300]
    return f"model server returned HTTP {status}: {detail or '(no detail)'}"


def _normalize_tool_calls(tool_calls: list[dict]) -> list[dict]:
    out = []
    for i, tc in enumerate(tool_calls):
        fn = tc.get("function", {})
        out.append({
            "id": tc.get("id") or f"call_{i}",
            "type": "function",
            "function": {
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", "") or "{}",
            },
        })
    return out
