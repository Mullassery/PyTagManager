import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "observability"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Access-log lines otherwise land on stderr, which Click's
        # CliRunner captures into result.output -- polluting tests that
        # assert on exact CLI output (e.g. parsing --format json).
        pass


@pytest.fixture(scope="session")
def fixture_server():
    """Serves tests/python/fixtures/observability/ over local HTTP so
    Playwright-driven observability tests run against a real http:// origin
    (avoiding file:// URL quirks around fetch()/history.pushState) without
    any real network access.
    """
    handler = functools.partial(_QuietHandler, directory=str(_FIXTURES_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


class _CapturingWebhookHandler(http.server.BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CapturingWebhookHandler.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def capturing_webhook_server():
    """A real local HTTP server that captures JSON POST bodies -- used to
    test WebhookNotifier and the CLI's --alert-webhook wiring without
    mocking urllib."""
    _CapturingWebhookHandler.received = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _CapturingWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", _CapturingWebhookHandler.received
    finally:
        server.shutdown()
        thread.join(timeout=5)
