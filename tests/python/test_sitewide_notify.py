"""Tests WebhookNotifier against a real local HTTP server -- no mocked
urllib, so this exercises the actual request construction/serialization,
matching the "no fake stubs" bar the rest of this test suite holds to.
"""

import http.server
import threading

import pytest

from pytagmanager.sitewide.notify import WebhookNotifier


class _FailingHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(500)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def failing_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _FailingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_webhook_notifier_posts_slack_compatible_payload(capturing_webhook_server):
    url, received = capturing_webhook_server
    notifier = WebhookNotifier(url)
    sent = notifier.send("Tracking health regression on example.com")

    assert sent is True
    assert received == [{"text": "Tracking health regression on example.com"}]


def test_webhook_notifier_returns_false_on_server_error(failing_server):
    notifier = WebhookNotifier(failing_server)
    assert notifier.send("test") is False


def test_webhook_notifier_returns_false_when_unreachable():
    notifier = WebhookNotifier("http://127.0.0.1:1", timeout=1.0)
    assert notifier.send("test") is False
