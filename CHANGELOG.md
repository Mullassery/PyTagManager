# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project does not yet follow semantic versioning strictly (see
`ROADMAP_HONEST.md` for current version/PyPI status).

Entries below are derived from the actual git history and PyPI publish
notes, not reconstructed from memory — see `ROADMAP_HONEST.md` for the
authoritative, continuously-updated built-vs-not-built breakdown; this
file is a release-oriented complement to it, not a duplicate.

## [Unreleased]

### Added
- GTM container JSON/YAML inspection with findings, best-effort draft
  import/export and the `gtm` CLI; imports never activate a container.
- Self-hosted control plane for containers, revisions, environments,
  publication/rollback, revision diffs, audit sequence and secret references,
  plus conservative PyTagShield configuration export.
- Shared event contract v1, secret-free published configuration with SHA-256
  integrity, filesystem CDN publication, a collection endpoint with in-memory
  or durable SQLite deduplication, and optional PyTagShield forwarding.
- Web, iOS and Android SDKs with strict validation, consent-aware queues,
  batching/retry, auto-flush, bounded local storage and sanitized debug
  snapshots.
- Collection deployment examples, Android/Web/iOS CI jobs and GTM-focused
  getting-started documentation.
- `pytagmanager lighthouse-ci`: repeated Lighthouse runs aggregated by median
  with observed ranges, failed-run retention, explicit budgets, confidence and
  limitations. A single run is no longer presented as a performance verdict.
- `pytagmanager cmp audit`: evidence-backed CMP detection (Cookiebot, OneTrust,
  Usercentrics, Didomi, Quantcast, TrustArc, Osano, Google Funding Choices),
  Cookiebot/Google Consent Mode state, pre/post-choice request ordering, reload
  persistence checks, stable findings and a v1 JSON schema. Read-only by
  default; consent interaction requires explicit authorization. Reports never
  include raw cookie values or request query strings.

### Fixed
- Base `pytagmanager` CLI imports no longer require the optional `yaml` or
  Playwright diagnostics dependencies.
- Built wheels now bundle the Web SDK asset, so CDN publication works from a
  fresh install instead of depending on an untracked `sdk/web/dist` directory.
- Web SDK retry timer no longer leaves a stale retry deadline that could
  suppress later retries.

## [0.5.0] - 2026-10-19

### Added
- `pytagmanager gtm-plan --generated out.json --container GTM-XXXX --credentials sa.json`
  compares a generated container export with the live GTM container and reports
  added/existing/conflicting tags, triggers, and variables. Read-only; never
  writes to GTM. Exits 1 when conflicts exist. Unit tests cover the planner.

## [0.4.1] - 2026-10-19

### Added
- `diagnose --site-wide --history ... --fail-on-regression`: exits `1` when
  the previous run's site/template health score dropped by the configured
  threshold, so scheduled CI jobs can fail without parsing the report.

## [0.4.0] - 2026-10-19

### Added
- Data Dictionary GTM cross-referencing (`--gtm-config` / `--gtm-container`
  with `--gtm-credentials`): maps each observed dataLayer field to the GTM
  tags, triggers, and variables that consume it (via Data Layer Variables),
  and adds a GTM blast-radius section to `--compare-to` drift reports.
  Matching is exact/dot-suffix only; no speculative field-to-tag claims.

## [0.3.5] - 2026-10-18

### Added
- Interactive standalone HTML/SVG rendering of the Tag Execution Graph (`build_graph_html`), plus a `--tag-graph-html PATH` option on `diagnose` that writes it. The file embeds the graph JSON (safely escaped) and needs no server or external assets: one column per node kind, edges dashed by evidence strength, hover tooltips, and click-to-highlight of a node's neighbourhood (RECHECK-052).

## [0.3.4] - 2026-10-18

### Added
- Runnable TypeScript Playwright export (`export_playwright_ts_script`), alongside the Python draft, and a `playwright_ts_draft` field in the JSON report. The Python draft stays deliberately non-runnable (`raise NotImplementedError`); the TypeScript spec is a valid spec a Playwright runner will execute, but calls `test.fixme(...)` unconditionally so an unreviewed draft is reported as pending, never passed (RECHECK-051).

## [0.3.3] - 2026-10-18

### Changed
- Depend on MudFish's Rust crates via the release tag `rust-v0.1.3` instead of
  the raw commit `71176fa`, so crawler-framework upgrades are deliberate and
  revertible (part of the cross-repo MudFish pilot).
- Migrated to MudFish's `BrowserRenderer::launch(chrome_path: Option<&Path>)`
  signature (`launch(None)`, i.e. host Chrome) introduced in `rust-v0.1.3`.
- Aligned `Cargo.toml` version with `pyproject.toml`/`__version__`.

## [0.3.2] - 2026-10-17

### Fixed
- Audit remediation: security hardening, correctness fixes, and lint/CI gates.

## [0.3.1] - 2026-10-12

### Fixed

- **The Phase 1.8 interactive-element objectives had no canonical event
  mapping, so seven of the fourteen objectives the heuristics engine can
  emit silently fell through to the generic fallback in every exporter.**
  `recommend/heuristics.py` can produce `Cart Modification`, `Wishlist
  Intent`, `Content Discovery`, `Pagination`, `Video Engagement`,
  `Navigation`, and `Modal Interaction`, but `export/_taxonomy.py`'s
  `CANONICAL_EVENT_MAP` only covered the original seven, so those
  recommendations exported as the platform-neutral `custom_event` (and,
  in GA4/Segment/RudderStack, as their generic default event name). Added
  real, platform-neutral canonical keys (`remove_from_cart`,
  `add_to_wishlist`, `content_discovery`, `pagination`,
  `video_engagement`, `navigation`, `modal_interaction`) plus matching
  spec entries in `ga4.py` (using GA4's documented `remove_from_cart` /
  `add_to_wishlist` / `video_start` recommended events where they exist),
  `segment.py`, and `rudderstack.py` (e.g. Segment's Ecommerce v2 spec
  name `Product Removed`). `intent/ollama_classifier.py`'s `_TAXONOMY`,
  despite a comment claiming it "matches recommend/heuristics.py's
  taxonomy," was also missing these seven — so the LLM classification
  path could never emit them either; it now matches. New tests in
  `tests/python/test_exporters.py` assert every heuristic objective has a
  non-fallback canonical event, every canonical event has a spec entry in
  all three name-mapping exporters, and the Ollama taxonomy equals the
  heuristic taxonomy exactly.

## [0.3.0] - 2026-10-04

### Changed

- Crawl engine now runs on Mudfish (`mudfish-core`/`mudfish-frontier`/
  `mudfish-fetch`/`mudfish-browser`, git dependencies on
  `github.com/Mullassery/MudFish`) instead of this crate's own
  fetcher/frontier/robots implementation, which has been deleted
  (`src/crawler/{fetcher,frontier,robots}.rs`). `Page` gained
  `crawl_status`, `rendered`, `network_requests`, and `cookies` fields.
  New `crawl_site(..., browser_mode="off"|"auto"|"always")` /
  `pytagmanager crawl --browser {off,auto,always}` option (default `off`,
  no behavior change) for lightweight per-page browser rendering via
  Mudfish's real headless-Chrome engine. See `ROADMAP_HONEST.md` for the
  disclosed limitations (notably: the browser-render path doesn't go
  through Mudfish's SSRF guard yet).

## [0.2.2] - 2026-09-27

### Fixed

- `src/crawler/frontier.rs`: `Frontier::has_capacity()` no longer also checks
  `seen.len() < max_pages` -- that extra check caused the BFS loop to exit as
  soon as `seen` (URLs *discovered*, not fetched) reached `max_pages`, even
  while already-accepted URLs were still sitting unfetched in the queue.
  Concretely, `crawl(url, max_pages=1)` returned zero pages instead of the
  seed page it should always return. See `ROADMAP_HONEST.md` for full
  verification detail and the regression tests added.

## [0.2.1] - 2026-09-22

Everything shipped on `main` since the v0.2.0 version bump (2026-08-31),
published to PyPI as v0.2.1 on 2026-09-22 — see `ROADMAP_HONEST.md`'s CI/CD
section for the current PyPI status. Highlights, in shipped order:

- Tracking Observability & Diagnostics: Runtime State Capture (cookies/
  storage/dataLayer snapshots + diffing), Website Data Dictionary (schema
  drift, presence-vs-availability labeling, purpose classification),
  broadened browser-behavior intelligence (scroll-depth interactions,
  cross-implementation consistency checks, Runtime Event Map, formalized
  Interaction Trace).
- GTM Client/Server Execution Intelligence & Tag Execution Graph:
  static tag/vendor scanning (`scan-tags`), duplicate/conflicting
  implementation detection, hedged server-side tagging indicators, and
  the unified Tag Execution Graph (`diagnose --tag-graph`).
- Playwright Discovery & Test Intelligence: evidence-backed Test
  Candidates generated from diagnosis/consistency/regression findings,
  with Playwright draft-script export.
- Automated Script Impact & Web Performance Intelligence
  (`pytagmanager perf`): real browser-native performance measurement,
  script inventory + dependency graph, controlled isolation experiments,
  tagging-vs-performance join, CPU throttling, and history/regression
  tracking.
- Client-rendered crawling (`crawl --render`): rendered-DOM discovery,
  per-page screenshot capture, analytics sniffing, and bounded
  interaction simulation for sites whose content only exists after JS
  runs.
- `OllamaIntentClassifier` wired directly into `crawl --intent ollama`
  and the public `pytagmanager` API (previously implemented but not
  reachable from the CLI).
- `Cargo.toml` version drift fix (was stuck at 0.1.3 while
  `pyproject.toml`/`__init__.py` had already moved to 0.2.0).
- CI fix: `ci.yml` now installs the `pytagmanager[diagnostics]` extra and
  a Playwright Chromium binary before running `pytest` — previously every
  push since Tracking Observability landed failed pytest's collection
  phase outright (`ModuleNotFoundError: No module named 'yaml'`).

### Fixed

- `src/lib.rs`: the `crawl()` pyfunction no longer panics (via PyO3's
  panic-to-`PanicException` conversion) if `tokio::runtime::Runtime::new()`
  fails — the failure now propagates as a catchable Python `RuntimeError`
  through a new `AppError::Internal` variant.
- `src/crawler/fetcher.rs`: `Fetcher::build()` no longer panics if
  `reqwest::Client::builder().build()` fails — propagated through the
  `Result<Self, AppError>` the function already returns, same as its other
  failure modes.
- `src/crawler/orchestrator.rs`: corrected a stale doc comment on
  `crawl_with_fetcher` claiming the real entry point calls `Fetcher::new()`
  — it actually calls `Fetcher::build(true, ...)` directly.

See `ROADMAP_HONEST.md` for exactly which sub-items of the above are
fully shipped vs. disclosed-partial, and for known bugs/tech debt, plus
the now-verified (and currently red) `dependency-audit` CI job results.

## [0.2.0] — version bumped in repo 2026-08-31, published to PyPI 2026-09-14

No git tag exists for this release in this repository as of this writing.

- Relicensed the project from a proprietary license to Apache-2.0.
- Added Tracking Observability & Diagnostics (real-browser interaction →
  dataLayer → GTM → GA4 correlation, rule-based root-cause diagnosis) and
  Site-Wide Tagging QA (cross-page template consistency, health scoring).
- **PyPI platform coverage note**: this release published only a macOS
  arm64 wheel + sdist (no Docker/zig available locally for manylinux
  cross-compilation at publish time), narrower than v0.1.3's release
  (macOS x86_64 + arm64 + Linux x86_64 + aarch64 + sdist). See
  `ROADMAP_HONEST.md` for detail.

## [0.1.3] — 2026-08-26

- Added non-GTM exporters (GA4, Segment, Snowplow, Tealium, RudderStack,
  Adobe Tags).
- Added crawl-to-crawl diffing (`pytagmanager diff`).
- Added `OllamaIntentClassifier` (local-LLM business-intent
  classification via Ollama).
- Published a proprietary LICENSE for the initial public release (later
  superseded by the Apache-2.0 relicense in 0.2.0).
- CI fix: create and activate a virtualenv before `maturin develop`.
- Added README metadata + `abi3-py39` PyO3 feature for broader wheel
  compatibility.

## [0.1.1] — 2026-08-12

- Added an SSRF guard to the Rust crawler (blocks loopback and cloud
  metadata-service addresses).
- Added the Rust/Python integration test suite and initial CI workflow.

## [0.1.0] — initial commit

- Rust crawler (BFS, sitemap.xml, robots.txt) + semantic DOM graph engine
  (selectors, ARIA).
- Rule-based tracking recommendation engine.
- CLI (`pytagmanager crawl`) + GTM export.
- Initial product vision and roadmap documents.
