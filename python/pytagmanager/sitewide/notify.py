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
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

# Statuses worth retrying: explicit throttling plus transient server errors.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@runtime_checkable
class Notifier(Protocol):
    def send(self, message: str) -> bool: ...


class WebhookNotifier:
    """POSTs `{"text": message}` to any webhook URL that accepts that
    shape -- this is Slack's incoming-webhook payload format, and also
    what most generic internal alerting endpoints expect, so one
    implementation covers both without a Slack-specific SDK dependency.
    """

    def __init__(
        self,
        url: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        min_interval: float = 0.0,
    ):
        self.url = url
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        # Minimum spacing between sends (seconds). This is the token-bucket
        # pacing that protects a downstream endpoint during alert bursts;
        # 0 disables pacing.
        self.min_interval = max(0.0, min_interval)
        self._next_allowed = 0.0
        self._pacing_lock = threading.Lock()

    def _pace(self) -> None:
        if self.min_interval <= 0:
            return
        with self._pacing_lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                time.sleep(wait)
            self._next_allowed = max(now, self._next_allowed) + self.min_interval

    @staticmethod
    def _backoff_delay(attempt: int, retry_after: str | None) -> float:
        """Exponential backoff with jitter, honoring `Retry-After` (seconds)."""
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 60.0))
            except ValueError:
                pass
        return min(30.0, (2.0**attempt)) + random.uniform(0.0, 0.5)

    def send(self, message: str) -> bool:
        payload = json.dumps({"text": message}).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        retry_after: str | None = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            retry_after = None
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if 200 <= response.status < 300:
                        return True
                    if response.status not in _RETRYABLE_STATUS:
                        return False
                    retry_after = response.headers.get("Retry-After")
            except urllib.error.HTTPError as exc:
                if exc.code not in _RETRYABLE_STATUS:
                    return False
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
            except (urllib.error.URLError, OSError, TimeoutError):
                retry_after = None
            if attempt < self.max_retries:
                time.sleep(self._backoff_delay(attempt, retry_after))
        return False
