"""Minimal HTTP collection endpoint with CORS and bounded request handling."""

from __future__ import annotations

import hmac
import json
import logging
import ssl
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pytagmanager.control.errors import ValidationError

from .service import IngestService

LOGGER = logging.getLogger("pytagmanager.ingest")


class IngestHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, address, handler, service: IngestService, ssl_context=None):
        self.ingest_service = service
        self.ssl_context = ssl_context
        super().__init__(address, handler)

    def get_request(self):
        sock, address = super().get_request()
        if self.ssl_context is not None:
            sock = self.ssl_context.wrap_socket(sock, server_side=True)
        return sock, address

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self.ingest_service.close()


class IngestHandler(BaseHTTPRequestHandler):
    server_version = "pytagmanager-ingest"
    sys_version = ""
    timeout = 20

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.info("%s %s", self.address_string(), fmt % args)

    def _service(self) -> IngestService:
        return self.server.ingest_service  # type: ignore[attr-defined]

    def _origin(self) -> str | None:
        return self.headers.get("Origin")

    def _allowed_origin(self) -> str | None:
        origin = self._origin()
        if not origin:
            return None
        allowed = self._service().config.cors_origins
        if "*" in allowed:
            return "*"
        return origin if origin in allowed else None

    def _cors_headers(self) -> dict[str, str]:
        allowed = self._allowed_origin()
        if allowed is None:
            return {}
        headers = {
            "Access-Control-Allow-Origin": allowed,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
            "Access-Control-Max-Age": "600",
        }
        if allowed != "*":
            headers["Vary"] = "Origin"
        return headers

    def _send(self, status: int, payload: dict[str, Any], *, origin: str | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urllib.parse.urlsplit(self.path).path != self._service().config.path:
            self._send(404, {"error": "not_found"})
            return
        self.send_response(204)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urllib.parse.urlsplit(self.path).path == "/healthz":
            service = self._service()
            self._send(
                200,
                {
                    "status": "ok",
                    "forwarding_configured": service.forwarder is not None,
                    "dedupe_backend": service.dedupe.backend,
                    "max_body_bytes": service.config.max_body_bytes,
                    "max_batch_events": service.config.max_batch_events,
                },
            )
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urllib.parse.urlsplit(self.path).path != self._service().config.path:
            self._send(404, {"error": "not_found"})
            return
        service = self._service()
        if not self._authorized(service):
            self._send(401, {"error": "unauthorized"})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send(415, {"error": "unsupported_media_type"})
            return
        length_text = self.headers.get("Content-Length")
        if length_text is None:
            self._send(411, {"error": "content_length_required"})
            return
        try:
            length = int(length_text)
        except ValueError:
            self._send(400, {"error": "invalid_content_length"})
            return
        if length < 1 or length > service.config.max_body_bytes:
            self._send(413, {"error": "request_too_large"})
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self._send(400, {"error": "incomplete_request_body"})
            return
        try:
            raw = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "invalid_json"})
            return
        if not isinstance(raw, dict):
            self._send(400, {"error": "invalid_payload"})
            return
        client_ip = self.client_address[0] if self.client_address else None

        if isinstance(raw.get("events"), list):
            result = service.ingest_batch(raw, client_ip=client_ip)
            if result["status"] == "accepted":
                status = 202
            elif result["status"] == "rate_limited":
                status = 429
            elif result["status"] == "rejected" and not result.get("results"):
                status = 400
            elif result["status"] == "rejected":
                status = 422
            else:
                status = 207
            self._send(status, result)
            return

        result = service.ingest_event(raw, client_ip=client_ip)
        status = self._status_for(result.status, result.retryable)
        self._send(status, result.to_dict())

    def _authorized(self, service: IngestService) -> bool:
        if service.api_token is None:
            return True
        supplied = self.headers.get("Authorization", "")
        if supplied.lower().startswith("bearer "):
            supplied = supplied[7:].strip()
        elif self.headers.get("X-API-Key"):
            supplied = self.headers["X-API-Key"].strip()
        return bool(supplied) and hmac.compare_digest(supplied, service.api_token)

    @staticmethod
    def _status_for(status: str, retryable: bool) -> int:
        if status in {"accepted", "forwarded", "duplicate", "in_progress"}:
            return 202
        if status == "rate_limited":
            return 429
        if retryable:
            return 503
        return 422


def create_server(
    service: IngestService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    ssl_context: ssl.SSLContext | None = None,
) -> IngestHTTPServer:
    return IngestHTTPServer((host, port), IngestHandler, service, ssl_context=ssl_context)


def make_ssl_context(certfile: str, keyfile: str) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return context


def serve(
    service: IngestService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    ssl_context: ssl.SSLContext | None = None,
) -> None:
    server = create_server(service, host=host, port=port, ssl_context=ssl_context)
    try:
        server.serve_forever()
    finally:
        server.server_close()
