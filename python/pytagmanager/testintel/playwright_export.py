"""Playwright export (docs/VISION.md §15, Phase 1.9 item 4): a draft
Playwright script per Test Candidate, always paired with the evidence
that produced it.

"The product may emit Playwright pseudocode or a draft implementation,
but the required output is test *intent* plus *evidence* -- a draft
script without traceable evidence is not a shippable Test Candidate."
Every export here leads with a docstring naming the candidate's category,
severity, observed problem, and evidence pages before a single line of
test code -- and the generated test body always ends in
`raise NotImplementedError`, so a draft can never be mistaken for a
passing (or even runnable) verified test if someone runs it unreviewed.
Filling in the real selectors/assertions from the evidence and suggested
verification steps is exactly the human review step VISION.md §15's
pipeline calls for before a Test Candidate becomes a real Playwright test.
"""

from __future__ import annotations

import re

from pytagmanager.testintel.candidates import TestCandidate

_MAX_EVIDENCE_PAGES_LISTED = 10


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "candidate"


def export_playwright_script(candidate: TestCandidate) -> str:
    evidence_lines = [f"  - {url}" for url in candidate.evidence_pages[:_MAX_EVIDENCE_PAGES_LISTED]]
    remaining = candidate.evidence_count - len(evidence_lines)
    if remaining > 0:
        evidence_lines.append(f"  ... and {remaining} more")
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "  (no page-level evidence recorded)"

    step_comments = "\n".join(f"    # Step {i}: {step}" for i, step in enumerate(candidate.suggested_verification, start=1))
    if not step_comments:
        step_comments = "    # No suggested verification steps were generated for this category."

    return f'''"""
Test Candidate: {candidate.name}
Category: {candidate.category} | Severity: {candidate.severity}

Observed: {candidate.observed}
Observed problem: {candidate.observed_problem}

Evidence ({candidate.evidence_count} page(s)):
{evidence_block}

This is a DRAFT generated from automated discovery, not a verified test.
Review before running: fill in the real page URL(s) from Evidence above,
confirm selectors, and replace the placeholder assertions.
"""

from playwright.sync_api import Page, expect


def test_{_slugify(candidate.name)}(page: Page) -> None:
{step_comments}
    # TODO: implement the steps above against a real page URL from Evidence.
    raise NotImplementedError("draft Test Candidate -- fill in before running")
'''


def _escape_ts_comment(text: str) -> str:
    return text.replace("*/", "* /")


def _escape_ts_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def export_playwright_ts_script(candidate: TestCandidate) -> str:
    """Emit the draft as a *runnable* TypeScript Playwright spec.

    The Python draft (``export_playwright_script``) intentionally ends in
    ``raise NotImplementedError`` so it can never pass unreviewed. That makes it
    Python-only and not runnable as-is. This TypeScript variant is both: it is a
    valid spec that a Playwright runner will load and execute, but it calls
    ``test.fixme(...)`` unconditionally, so an unreviewed draft is reported as
    pending rather than passed -- it cannot masquerade as a green test.
    """
    evidence_lines = [
        f" *   - {url}" for url in candidate.evidence_pages[:_MAX_EVIDENCE_PAGES_LISTED]
    ]
    remaining = candidate.evidence_count - len(evidence_lines)
    if remaining > 0:
        evidence_lines.append(f" *   ... and {remaining} more")
    if not evidence_lines:
        evidence_lines.append(" *   (no page-level evidence recorded)")
    evidence_block = "\n".join(evidence_lines)

    step_comments = "\n".join(
        f"  // Step {i}: {step}" for i, step in enumerate(candidate.suggested_verification, start=1)
    )
    if not step_comments:
        step_comments = "  // No suggested verification steps were generated for this category."

    default_url = candidate.evidence_pages[0] if candidate.evidence_pages else "<fill-in-from-evidence>"

    header = "\n".join(
        " * " + _escape_ts_comment(line)
        for line in (
            f"Test Candidate: {candidate.name}",
            f"Category: {candidate.category} | Severity: {candidate.severity}",
            "",
            f"Observed: {candidate.observed}",
            f"Observed problem: {candidate.observed_problem}",
            "",
            f"Evidence ({candidate.evidence_count} page(s)):",
        )
    )

    return f'''/*
{header}
{evidence_block}
 *
 * This is a DRAFT generated from automated discovery, not a verified test.
 * Review before running: confirm the page URL(s), selectors and assertions,
 * then remove the test.fixme(...) call below.
 */
import {{ test, expect }} from '@playwright/test';

const TARGET_URL = process.env.TARGET_URL ?? '{_escape_ts_string(default_url)}';

test('{_escape_ts_string(candidate.name)}', async ({{ page }}) => {{
  test.fixme(true, 'Draft Test Candidate -- fill in steps/selectors/assertions, then remove this.');

{step_comments}
  await page.goto(TARGET_URL);
  // TODO: implement the steps above against TARGET_URL and add assertions.
  expect(page).toBeTruthy();
}});
'''

