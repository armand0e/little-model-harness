"""Tiny deterministic OpenAI-compatible server for browser smoke tests."""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def _json(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._json({"data": [{"id": "smoke", "owned_by": "tests",
                                   "meta": {"n_ctx": 32768}}]})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        users = [m.get("content", "") for m in request.get("messages", [])
                 if m.get("role") == "user"]
        last = str(users[-1]) if users else ""
        if "steering update" in last.lower():
            words = "Steering applied at the safe boundary. I changed direction as requested.".split()
        elif "queued follow-up" in last.lower():
            words = "Queued follow-up completed after the original turn.".split()
        else:
            words = ("Working on the original request before any queued follow-up. " * 8).split()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for word in words:
            chunk = {"choices": [{"delta": {"content": word + " "},
                                    "finish_reason": None}]}
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.flush()
            time.sleep(0.07)
        done = {"choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": len(words)}}
        self.wfile.write(("data: " + json.dumps(done) + "\n\n"
                          "data: [DONE]\n\n").encode())
        self.wfile.flush()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
