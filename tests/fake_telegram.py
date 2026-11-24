"""A tiny fake Telegram Bot API server for tests (no internet, no real bot).

Tests put "incoming" phone messages in with `fake.send_from_phone(...)` and
read what the bot answered in `fake.sent`.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "123:TEST"


class FakeTelegram:
    def __init__(self):
        self.pending: list[dict] = []
        self.sent: list[dict] = []
        self._next_update = 1
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                prefix = f"/bot{TOKEN}/"
                if not self.path.startswith(prefix):
                    self._reply(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
                    return
                method = self.path[len(prefix):]
                if method == "getMe":
                    self._reply(200, {"ok": True, "result": {"id": 1, "username": "TestBot"}})
                elif method == "getUpdates":
                    offset = body.get("offset") or 0
                    with fake._lock:
                        fake.pending = [u for u in fake.pending if u["update_id"] >= offset]
                        result = list(fake.pending)
                    self._reply(200, {"ok": True, "result": result})
                elif method == "sendMessage":
                    with fake._lock:
                        fake.sent.append(body)
                    self._reply(200, {"ok": True, "result": {"message_id": len(fake.sent)}})
                else:
                    self._reply(404, {"ok": False, "description": "Not Found"})

        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass

        self.server = QuietServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def send_from_phone(self, text: str, user_id: int = 111, first_name: str = "Malak") -> None:
        with self._lock:
            self.pending.append({
                "update_id": self._next_update,
                "message": {"message_id": self._next_update, "text": text,
                            "chat": {"id": user_id, "type": "private"},
                            "from": {"id": user_id, "first_name": first_name}},
            })
            self._next_update += 1

    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
