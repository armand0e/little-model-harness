from __future__ import annotations

import httpx
import pytest
import threading
import time

import harness.llm as llm_module
from harness.llm import LLMClient


def client_with_stream(body: bytes) -> LLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={
            "content-type": "text/event-stream",
        })

    client = LLMClient("http://model.invalid/v1", "test")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_interrupted_model_stream_is_not_accepted_as_complete():
    client = client_with_stream(
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
    try:
        with pytest.raises(RuntimeError, match="before completion"):
            client.chat([], on_delta=lambda kind, text: None)
    finally:
        client.close()


def test_finish_reason_completes_stream_even_without_done_sentinel():
    client = client_with_stream(
        b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
        b'"usage":{"prompt_tokens":"4","completion_tokens":-2}}\n\n')
    try:
        response = client.chat([], on_delta=lambda kind, text: None)
        assert response.content == "ok"
        assert response.prompt_tokens == 4
        assert response.completion_tokens == 0
    finally:
        client.close()


def test_stream_reports_tool_argument_progress_without_exposing_content():
    client = client_with_stream(
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        b'"id":"call_1","function":{"name":"write_file",'
        b'"arguments":"{\\"path\\":\\"demo.html\\","}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        b'"function":{"arguments":"\\"content\\":\\"secret\\"}"}}]},'
        b'"finish_reason":"tool_calls"}]}\n\n')
    updates = []
    try:
        response = client.chat([], on_delta=lambda kind, text: updates.append(
            (kind, text)))
        assert response.tool_calls[0]["function"]["name"] == "write_file"
        assert [kind for kind, _ in updates] == ["tool", "tool"]
        assert '"arguments_chars"' in updates[-1][1]
        assert "secret" not in updates[-1][1]
    finally:
        client.close()


def test_stream_enforces_total_generation_deadline(monkeypatch):
    client = client_with_stream(
        b'data: {"choices":[{"delta":{"content":"still going"}}]}\n\n')
    client.timeout = 10
    ticks = iter([0.0, 11.0])
    monkeypatch.setattr(llm_module.time, "monotonic", lambda: next(ticks))
    try:
        with pytest.raises(TimeoutError, match="exceeded 10 seconds"):
            client.chat([], on_delta=lambda kind, text: None)
    finally:
        client.close()


def test_stream_retries_without_unsupported_stream_options():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        requests.append(payload)
        if "stream_options" in payload:
            return httpx.Response(400, json={
                "error": {"message": "unknown field stream_options"}})
        return httpx.Response(200, content=(
            b'data: {"choices":[{"delta":{"content":"ok"},'
            b'"finish_reason":"stop"}]}\n\n'), headers={
                "content-type": "text/event-stream"})

    client = LLMClient("http://model.invalid/v1", "test")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        response = client.chat([], on_delta=lambda kind, text: None)
        assert response.content == "ok"
        assert len(requests) == 2
        assert "stream_options" in requests[0]
        assert "stream_options" not in requests[1]
    finally:
        client.close()


def test_stream_accepts_common_reasoning_aliases():
    client = client_with_stream(
        b'data: {"choices":[{"delta":{"analysis":"thinking"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"answer"},'
        b'"finish_reason":"stop"}]}\n\n')
    updates = []
    try:
        response = client.chat([], on_delta=lambda kind, text: updates.append(
            (kind, text)))
        assert response.reasoning == "thinking"
        assert updates[0] == ("reasoning", "thinking")
    finally:
        client.close()


def test_cancel_current_closes_the_active_stream_promptly():
    class BlockingStream(httpx.SyncByteStream):
        def __init__(self):
            self.started = threading.Event()
            self.closed = threading.Event()

        def __iter__(self):
            self.started.set()
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            self.closed.wait(0.5)
            raise httpx.ReadError("stream closed")

        def close(self):
            self.closed.set()

    stream = BlockingStream()
    client = LLMClient("http://model.invalid/v1", "test")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=stream, headers={
            "content-type": "text/event-stream"})))
    result = []

    def generate():
        try:
            client.chat([], on_delta=lambda kind, text: None)
        except Exception as exc:  # assertion inspects the worker exception
            result.append(exc)

    worker = threading.Thread(target=generate)
    worker.start()
    assert stream.started.wait(1)
    started = time.monotonic()
    client.cancel_current()
    worker.join(2)
    try:
        assert not worker.is_alive()
        assert time.monotonic() - started < 1
        assert len(result) == 1
        assert "cancelled" in str(result[0])
    finally:
        client.close()
