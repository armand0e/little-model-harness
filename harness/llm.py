"""Minimal OpenAI-compatible chat client (llama.cpp / LM Studio / Ollama).

Supports streaming with incremental tool-call assembly. Reasoning models'
`reasoning_content` is surfaced separately and never stored in history.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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
        self.api_key = api_key
        self._client_lock = threading.RLock()
        self._response_lock = threading.RLock()
        self._active_response: httpx.Response | None = None
        self._cancel_event = threading.Event()
        self._client = self._new_client()

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _ensure_client(self) -> httpx.Client:
        with self._client_lock:
            if self._client.is_closed:
                self._client = self._new_client()
            return self._client

    def close(self) -> None:
        with self._client_lock:
            self._client.close()

    def cancel_current(self) -> None:
        """Interrupt the active response without waiting for its next token.

        Closing only the shared client is not a dependable cross-thread
        cancellation mechanism in httpx.  Keep hold of the actual streaming
        response and close that socket first; closing the client remains the
        fallback while a request is still waiting for response headers.
        """
        with self._response_lock:
            response = self._active_response
        self._cancel_event.set()
        target = response.close if response is not None else self.close
        # Some synchronous transports serialize close() behind the active
        # iterator. Never make the stop endpoint wait on that transport lock.
        threading.Thread(target=target, name="lmh-model-cancel",
                         daemon=True).start()

    def reset_cancel(self) -> None:
        """Prepare for a later turn after the previous one was cancelled."""
        self._cancel_event.clear()

    def reconfigure(self, base_url: str, model: str, api_key: str = "not-needed") -> None:
        """Point this client at a different endpoint/model at runtime."""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        client = self._ensure_client()
        client.headers["Authorization"] = f"Bearer {api_key}"

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             temperature: float = 0.4, max_tokens: int = 2048,
             on_delta: Optional[Callable[[str, str], None]] = None) -> LLMResponse:
        """Send a chat completion. If on_delta is given, streams.

        on_delta(kind, text) is called with kind in
        {"content", "reasoning", "tool"}. Tool updates are compact JSON
        progress records rather than the potentially huge argument payload.
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
            try:
                return self._chat_stream(payload, on_delta)
            except RuntimeError as exc:
                # Several otherwise compatible local servers reject the
                # optional OpenAI stream_options field. A 4xx occurs before
                # generation, so retrying without it cannot duplicate output.
                if ("HTTP 400" not in str(exc) and "HTTP 422" not in str(exc)):
                    raise
                payload.pop("stream_options", None)
                return self._chat_stream(payload, on_delta)
        return self._chat_once(payload)

    def _chat_once(self, payload: dict) -> LLMResponse:
        r = self._ensure_client().post(
            f"{self.base_url}/chat/completions", json=payload)
        if r.status_code >= 400:
            raise RuntimeError(_server_error(r.status_code, r.text))
        data = r.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        usage = data.get("usage") or {}
        return LLMResponse(
            content=msg.get("content") or "",
            reasoning=(msg.get("reasoning_content") or msg.get("reasoning")
                       or msg.get("analysis") or ""),
            tool_calls=_normalize_tool_calls(msg.get("tool_calls") or []),
            finish_reason=choice.get("finish_reason") or "",
            prompt_tokens=_nonnegative_int(usage.get("prompt_tokens")),
            completion_tokens=_nonnegative_int(usage.get("completion_tokens")),
        )

    def _chat_stream(self, payload: dict, on_delta: Callable[[str, str], None]) -> LLMResponse:
        resp = LLMResponse()
        started = time.monotonic()
        # tool calls arrive as indexed fragments; assemble by index
        pending: dict[int, dict] = {}
        items: queue.Queue[tuple[str, object]] = queue.Queue()
        client = self._ensure_client()

        def read_response() -> None:
            response: httpx.Response | None = None
            try:
                request = client.build_request(
                    "POST", f"{self.base_url}/chat/completions", json=payload)
                response = client.send(request, stream=True)
                with self._response_lock:
                    self._active_response = response
                if response.status_code >= 400:
                    response.read()
                    raise RuntimeError(_server_error(
                        response.status_code, response.text))
                for line in response.iter_lines():
                    items.put(("line", line))
            except BaseException as exc:
                items.put(("error", exc))
            finally:
                if response is not None:
                    response.close()
                with self._response_lock:
                    if self._active_response is response:
                        self._active_response = None
                items.put(("done", None))

        threading.Thread(target=read_response, name="lmh-model-stream-reader",
                         daemon=True).start()
        try:
            return self._consume_stream(items, on_delta, resp, pending, started)
        finally:
            # The transport worker owns response cleanup. The turn is allowed
            # to finish immediately even if a broken server never unblocks its
            # socket after cancellation.
            with self._response_lock:
                response = self._active_response
            if self._cancel_event.is_set() and response is not None:
                threading.Thread(target=response.close,
                                 name="lmh-model-response-close",
                                 daemon=True).start()

    def _consume_stream(self, items: queue.Queue[tuple[str, object]],
                        on_delta: Callable[[str, str], None],
                        resp: LLMResponse, pending: dict[int, dict],
                        started: float) -> LLMResponse:
        completed = False
        while True:
            if self._cancel_event.is_set():
                raise RuntimeError("model stream was cancelled")
            if time.monotonic() - started > self.timeout:
                raise TimeoutError(
                    f"model generation exceeded {self.timeout:g} seconds")
            try:
                kind, value = items.get(timeout=0.1)
            except queue.Empty:
                # httpx's read timeout is an idle timeout. A server dribbling
                # bytes could otherwise keep a request alive indefinitely.
                continue
            if kind == "error":
                exc = value
                if not isinstance(exc, BaseException):
                    exc = RuntimeError(str(exc))
                if self._cancel_event.is_set():
                    raise RuntimeError("model stream was cancelled") from exc
                if isinstance(exc, (httpx.ReadError, httpx.StreamClosed)):
                    raise RuntimeError("model stream was cancelled") from exc
                raise RuntimeError(f"model stream failed: {exc}") from exc
            if kind == "done":
                break
            line = str(value)
            if not line or not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                completed = True
                break
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            usage = data.get("usage")
            if usage:
                resp.prompt_tokens = _nonnegative_int(
                    usage.get("prompt_tokens"), resp.prompt_tokens)
                resp.completion_tokens = _nonnegative_int(
                    usage.get("completion_tokens"), resp.completion_tokens)
            choices = data.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            if choice.get("finish_reason"):
                resp.finish_reason = choice["finish_reason"]
                completed = True
            delta = choice.get("delta") or {}
            reasoning = (delta.get("reasoning_content")
                         or delta.get("reasoning")
                         or delta.get("analysis"))
            if reasoning:
                resp.reasoning += str(reasoning)
                on_delta("reasoning", str(reasoning))
            if delta.get("content"):
                resp.content += delta["content"]
                on_delta("content", delta["content"])
            for tc in delta.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                raw_idx = tc.get("index", 0)
                try:
                    idx = max(0, int(raw_idx))
                except (TypeError, ValueError, OverflowError):
                    idx = 0
                slot = pending.setdefault(idx, {
                    "id": "", "type": "function",
                    "function": {"name": "", "arguments": ""},
                })
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if not isinstance(fn, dict):
                    continue
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
                if tc.get("id") or fn.get("name") or fn.get("arguments"):
                    on_delta("tool", json.dumps({
                        "name": slot["function"]["name"],
                        "arguments_chars": len(
                            slot["function"]["arguments"]),
                    }))
        if not completed:
            raise RuntimeError("model server ended its stream before completion")
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


def _nonnegative_int(value: Any, fallback: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return fallback


def _normalize_tool_calls(tool_calls: list[dict]) -> list[dict]:
    out = []
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function", {})
        if not isinstance(fn, dict):
            fn = {}
        out.append({
            "id": tc.get("id") or f"call_{i}",
            "type": "function",
            "function": {
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", "") or "{}",
            },
        })
    return out
