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

Everything shipped on `main` since the v0.2.0 version bump (2026-08-31)
has **not** been published to PyPI yet — see `ROADMAP_HONEST.md`'s CI/CD
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

See `ROADMAP_HONEST.md` for exactly which sub-items of the above are
fully shipped vs. disclosed-partial, and for known bugs/tech debt.

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
