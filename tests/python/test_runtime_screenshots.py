"""Tests for `runtime.screenshots.capture_page_screenshots` (Phase 1 item
3) -- the phase's second exit criterion: screenshots are retrievable per
crawled page."""

from __future__ import annotations

from pytagmanager.runtime.screenshots import capture_page_screenshots, slug_for_url


def test_slug_for_url_is_filesystem_safe_and_stable():
    url = "http://127.0.0.1:8000/spa_client_rendered.html?x=1"
    slug = slug_for_url(url)
    assert slug == slug_for_url(url)
    assert "/" not in slug and ":" not in slug and "?" not in slug


def test_capture_page_screenshots_writes_four_real_png_files(fixture_server, tmp_path):
    url = f"{fixture_server}/spa_client_rendered.html"

    screenshots = capture_page_screenshots(url, tmp_path)

    for path in (
        screenshots.desktop_above_fold,
        screenshots.desktop_full_page,
        screenshots.mobile_above_fold,
        screenshots.mobile_full_page,
    ):
        assert path.exists(), f"{path} was not written"
        assert path.stat().st_size > 0
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert screenshots.url == url
