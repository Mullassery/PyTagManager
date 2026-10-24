"""Tests for Phase 1.9 item 4's Playwright export (docs/VISION.md §15):
every draft script must carry its evidence trail and must never be
runnable as a passing test without review."""

from __future__ import annotations

from pytagmanager.testintel.candidates import (
    CATEGORY_EVENT_EXISTENCE,
    SEVERITY_REQUIRES_VERIFICATION,
    TestCandidate,
)
from pytagmanager.testintel.playwright_export import (
    export_playwright_script,
    export_playwright_ts_script,
)
from pytagmanager.testintel.report import (
    build_test_candidates_json,
    render_test_candidates,
)


def _candidate(evidence_pages=("https://example.com/a", "https://example.com/b")):
    return TestCandidate(
        name="'add_to_cart' should fire a dataLayer event",
        category=CATEGORY_EVENT_EXISTENCE,
        severity=SEVERITY_REQUIRES_VERIFICATION,
        observed="'add_to_cart' event observed",
        observed_problem="No dataLayer event fired after the interaction.",
        evidence_pages=evidence_pages,
        suggested_verification=(
            "Trigger the interaction",
            "Assert an event was pushed",
        ),
        source_root_causes=("missing_datalayer_event",),
    )


def test_exported_script_names_the_category_severity_and_observed_problem():
    script = export_playwright_script(_candidate())
    assert "event_existence" in script
    assert "Requires verification" in script
    assert "No dataLayer event fired after the interaction." in script


def test_exported_script_lists_evidence_pages():
    script = export_playwright_script(_candidate())
    assert "https://example.com/a" in script
    assert "https://example.com/b" in script


def test_exported_script_caps_evidence_listing_and_notes_the_remainder():
    pages = tuple(f"https://example.com/page{i}" for i in range(15))
    script = export_playwright_script(_candidate(evidence_pages=pages))
    assert "https://example.com/page0" in script
    assert "and 5 more" in script


def test_exported_script_includes_suggested_verification_steps():
    script = export_playwright_script(_candidate())
    assert "Trigger the interaction" in script
    assert "Assert an event was pushed" in script


def test_exported_script_never_runnable_as_a_passing_test_without_review():
    script = export_playwright_script(_candidate())
    assert "raise NotImplementedError" in script
    assert "DRAFT" in script


def test_exported_script_is_syntactically_valid_python():
    script = export_playwright_script(_candidate())
    compile(script, "<test_candidate>", "exec")  # must not raise SyntaxError


def test_no_evidence_pages_still_produces_a_valid_script():
    script = export_playwright_script(_candidate(evidence_pages=()))
    assert "no page-level evidence recorded" in script
    compile(script, "<test_candidate>", "exec")


# ---- TypeScript export ----


def test_ts_script_is_playwright_typescript_and_runnable():
    script = export_playwright_ts_script(_candidate())
    assert "from '@playwright/test'" in script
    assert "async ({ page })" in script
    assert "await page.goto(TARGET_URL)" in script


def test_ts_script_marked_fixme_so_it_cannot_pass_unreviewed():
    script = export_playwright_ts_script(_candidate())
    assert "test.fixme(true" in script
    assert "DRAFT" in script


def test_ts_script_defaults_target_url_to_first_evidence_page():
    script = export_playwright_ts_script(_candidate())
    assert "process.env.TARGET_URL ?? 'https://example.com/a'" in script


def test_ts_script_without_evidence_uses_placeholder_url():
    script = export_playwright_ts_script(_candidate(evidence_pages=()))
    assert "process.env.TARGET_URL ?? '<fill-in-from-evidence>'" in script


def test_ts_script_escapes_single_quotes_in_name():
    script = export_playwright_ts_script(_candidate())
    # The candidate name contains a single quote; it must be escaped, not break
    # the string literal.
    assert "\\'add_to_cart\\'" in script


def test_ts_script_caps_evidence_listing_and_notes_the_remainder():
    pages = tuple(f"https://example.com/page{i}" for i in range(15))
    script = export_playwright_ts_script(_candidate(evidence_pages=pages))
    assert "https://example.com/page0" in script
    assert "and 5 more" in script


def test_ts_script_includes_suggested_verification_steps():
    script = export_playwright_ts_script(_candidate())
    assert "Trigger the interaction" in script
    assert "Assert an event was pushed" in script


# ---- report rendering ----


def test_build_test_candidates_json_includes_playwright_draft_by_default():
    payload = build_test_candidates_json([_candidate()])
    assert len(payload) == 1
    assert "raise NotImplementedError" in payload[0]["playwright_draft"]


def test_build_test_candidates_json_can_omit_playwright_draft():
    payload = build_test_candidates_json([_candidate()], include_playwright_draft=False)
    assert "playwright_draft" not in payload[0]


def test_build_test_candidates_json_includes_playwright_ts_draft_by_default():
    payload = build_test_candidates_json([_candidate()])
    assert "test.fixme(true" in payload[0]["playwright_ts_draft"]


def test_render_test_candidates_empty_list_returns_empty():
    assert render_test_candidates([]) == []


def test_render_test_candidates_includes_name_and_evidence_count():
    lines = render_test_candidates([_candidate()])
    joined = "\n".join(lines)
    assert "add_to_cart" in joined
    assert "2 page(s)" in joined
