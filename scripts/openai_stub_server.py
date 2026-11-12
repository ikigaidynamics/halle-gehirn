"""Minimaler OpenAI-kompatibler Stub-Server fuer den Bundle-Smoke-Test.

Beantwortet GET /v1/models mit 200 (Readiness-Check) und POST /v1/embeddings
mit Dummy-Vektoren. Nur fuer Tests gedacht.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class StubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/v1/models"):
            payload = {"object": "list", "data": [{"id": "stub-model", "object": "model"}]}
            self._send(200, payload)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.startswith("/v1/embeddings"):
            body = {"data": [{"index": 0, "object": "embedding", "embedding": [0.1] * 8}]}
            self._send(200, body)
        else:
            self._send(404, {"error": "not found"})

    def _send(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 9099), StubHandler).serve_forever()
