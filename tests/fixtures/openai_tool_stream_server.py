"""OpenAI-compatible fixture that slowly streams a large tool call."""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass  # expected when the browser exercises the Stop button

    def do_GET(self) -> None:
        if self.path != "/v1/models":
            self.send_error(404)
            return
        data = json.dumps({"data": [{"id": "slow-tool",
                                     "meta": {"n_ctx": 8192}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(size))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        if any(message.get("role") == "tool"
               for message in request.get("messages", [])):
            self._event({"choices": [{"delta": {"content": "Finished."},
                                       "finish_reason": "stop"}]})
            return
        self._event({"choices": [{"delta": {
            "reasoning_content": "I will build the page now."}}]})
        prefix = '{"path":"demo.html","content":"'
        self._tool(prefix, name="write_file", call_id="call_slow")
        for _ in range(24):
            time.sleep(0.5)
            self._tool("x" * 600)
        self._tool('"}')
        self._event({"choices": [{"delta": {},
                                   "finish_reason": "tool_calls"}]})

    def _tool(self, arguments: str, name: str = "", call_id: str = "") -> None:
        function = {"arguments": arguments}
        if name:
            function["name"] = name
        item = {"index": 0, "function": function}
        if call_id:
            item["id"] = call_id
        self._event({"choices": [{"delta": {"tool_calls": [item]}}]})

    def _event(self, payload: dict) -> None:
        self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode())
        self.wfile.flush()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
