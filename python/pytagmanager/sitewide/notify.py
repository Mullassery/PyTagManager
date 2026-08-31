"""Webhook alerting for tracking-health regressions
(`sitewide.history.detect_regression`). Stdlib-only (`urllib`), no SDK
dependency -- the same "no external package for a simple HTTP call"
choice already made in `intent/ollama_classifier.py`.

Scheduling recurring `diagnose --site-wide` runs -- and so, how often this
ever gets a chance to fire -- is left entirely to the caller's own
cron/CI; this module only sends one alert when explicitly called.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    def send(self, message: str) -> bool: ...


class WebhookNotifier:
    """POSTs `{"text": message}` to any webhook URL that accepts that
    shape -- this is Slack's incoming-webhook payload format, and also
    what most generic internal alerting endpoints expect, so one
    implementation covers both without a Slack-specific SDK dependency.
    """

    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout

    def send(self, message: str) -> bool:
        payload = json.dumps({"text": message}).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
