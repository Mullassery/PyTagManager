"""Regression tests for webhook backoff/pacing (Gemini review fix)."""

from pytagmanager.sitewide.notify import WebhookNotifier


def test_backoff_honors_retry_after_and_clamps():
    assert WebhookNotifier._backoff_delay(0, "7") == 7.0
    assert WebhookNotifier._backoff_delay(0, "999") == 60.0
    assert WebhookNotifier._backoff_delay(0, "not-a-number") <= 1.5


def test_backoff_grows_and_is_bounded():
    assert 1.0 <= WebhookNotifier._backoff_delay(0, None) <= 1.5
    assert 2.0 <= WebhookNotifier._backoff_delay(1, None) <= 2.5
    assert WebhookNotifier._backoff_delay(20, None) <= 30.5
