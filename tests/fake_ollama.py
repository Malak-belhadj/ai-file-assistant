"""A tiny fake Ollama server for tests.

It listens on a random local port and imitates the two endpoints we use:
  GET  /api/tags  -> {"models": [{"name": ...}]}
  POST /api/chat  -> {"message": {"role": "assistant", "content": ...}}

The reply text is decided by `responder(last_user_message) -> str`, so tests
control exactly what "the model" says. Every request body is recorded in
`server.requests` so tests can check what Python sent to Ollama.
This lets us test the real HTTP code without downloading a model.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class FakeOllama:
    def __init__(self, responder: Callable[[str], str], models: list[str] | None = None,
                 chat_status: int = 200):
        self.responder = responder
        self.models = models if models is not None else ["qwen3.5:4b"]
        self.chat_status = chat_status
        self.requests: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _send(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/tags":
                    self._send(200, {"models": [{"name": m} for m in fake.models]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append(body)
                if self.path != "/api/chat":
                    self._send(404, {"error": "not found"})
                    return
                if body.get("model") not in fake.models:
                    self._send(404, {"error": f"model '{body.get('model')}' not found"})
                    return
                if fake.chat_status != 200:
                    self._send(fake.chat_status, {"error": "simulated server failure"})
                    return
                user_messages = [m["content"] for m in body.get("messages", []) if m["role"] == "user"]
                content = fake.responder(user_messages[-1] if user_messages else "")
                self._send(200, {"model": body["model"], "done": True,
                                 "message": {"role": "assistant", "content": content}})

        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass  # e.g. client gave up early in the timeout test; not a failure

        self.server = QuietServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOllama":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def unused_url() -> str:
    """A URL where nothing is listening (simulates 'Ollama not running')."""
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"
