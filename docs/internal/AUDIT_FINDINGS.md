# Audit findings — 2026-10-19

> **Historical audit.** This file predates v0.6.0 and is retained for context.
> Current integration status, security gaps, stubs and blockers are maintained
> in [`ECOSYSTEM_INTEGRATION.md`](../../ECOSYSTEM_INTEGRATION.md) and
> [`QUEUE_STATUS.md`](QUEUE_STATUS.md). Do not cite test counts or packaging
> claims from this file as current.

This file records the repository-specific findings from the portfolio audit
conducted on 2026-10-19. It is documentation only; no code or release artifacts
were changed in this pass unless explicitly noted under "Implementation status".

Sources: the repository's own README/source/workflows, GitHub metadata and
Actions runs, PyPI metadata, and official competitor documentation. Claims are
marked as verified, inferred, or open questions. "Absent" means not found in the
inspected repository/docs, not proof that it cannot exist.

## What it is

AI-native analytics implementation and verification: crawl sites, build a semantic DOM graph, recommend/export tags, build a data dictionary, diff snapshots, and verify runtime tracking in a real browser.

## Verified strengths

- 40 Rust + 404 Python tests; real Playwright runtime verification; journey scenarios; site-wide history/webhook alerts; 7 exporters; data dictionary; consent-blocking diagnosis; honest limitations.
- One of the most differentiated projects in the portfolio: open-source crawl-scale runtime tracking QA with cited evidence.

## Verified gaps and user-facing risks

- README is internally inconsistent (badge 0.3.1; install note says 0.1.3/0.2.1; PyPI 0.3.5).
- Only a macOS arm64 wheel; `main` CI failed on 2026-10-18.
- GTM export is a minimal container JSON for hand import, not the full schema/API; no hosted scheduler; no CMP/consent matrix.
- 7 exporters vs ObservePoint's ~96-provider coverage.

## Direct competitors

- ObservePoint (site/journey scans, alerts/API, consent validation, ~96 providers), GTM Tag Assistant, Adobe Experience Platform Debugger, Tealium.

## Ranked next actions

- P1: scheduled regression Action + alerting (M).
- P1: GTM API sync (read container, create workspace/tags/triggers) (M).
- P1: repair docs/version/wheel coverage (S).
- P2: consent/CMP validation matrix (M).

## Do not build

- Visual/screenshot grounding, XDM modeling, mobile/non-web platforms; explicitly deferred and not core.

## Evidence gaps / validation needed

- No precision/recall benchmark for recommendations; no user validation of diagnosis rules; GTM API credentials unavailable.

## Recommended disposition

Invest as a flagship; packaging and GTM API are the next milestones.

## Implementation status

Implemented the Phase 1.7 GTM remainder in this pass:

- New `dictionary/gtm_usage.py` indexes GTM Data Layer Variables and the
  tags/triggers/variables that reference them.
- `dictionary --gtm-config <export.json>` adds per-field `GTM consumers` to
  the text/JSON dictionary; `--compare-to` adds a `gtm_blast_radius` section.
- `--gtm-container` + `--gtm-credentials` fetch the live published container
  via the existing Management API client (added
  `GtmApiClient.get_live_container_document`).
- New `tests/test_gtm_usage.py` (5 tests) covers indexing, suffix matching,
  dictionary JSON/text, drift blast radius, and file loading.

Also added `diagnose --site-wide --history ... --fail-on-regression` (exit 1
on a score drop) with a GitHub Actions example in `docs/CI.md`.

Verification: `PYTHONPATH=python python3 -m pytest tests/test_gtm_usage.py
tests/python/test_dictionary_schema_drift.py` → 13 passed. The pre-existing
dictionary CLI tests require Playwright/Chromium, which is absent here.
