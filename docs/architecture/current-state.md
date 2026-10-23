# PyTagManager — Current State (Phase 0 Audit)

> **Historical baseline.** This audit records commit `92bc000` before the v0.6.0
> control plane, collection service and CMP work landed. Several "Unavailable"
> rows below are now outdated. For current integration status, security gaps and
> blockers, use [`../../ECOSYSTEM_INTEGRATION.md`](../../ECOSYSTEM_INTEGRATION.md)
> and [`../../QUEUE_STATUS.md`](../../QUEUE_STATUS.md).

- **Status:** Audit complete; no application code changed.
- **Audit date:** 2026-10-20
- **Repository:** `Mullassery/PyTagManager`
- **Branch/commit audited:** `main` @ `92bc000` (`test/docs: make lighthouse optional-dependency handling explicit`)
- **Package version:** `0.6.0` (`pyproject.toml`, `Cargo.toml`, `pytagmanager.__version__` agree)
- **License:** Apache-2.0

This document records what the repository **actually implements**, where it
lives, how it is reached, and what was verified by running the project. It is
the baseline against which every later phase must be checked.

---

## 1. Audit method and environment

Inspected:

- Rust core: `src/`, `Cargo.toml`, `Cargo.lock`, `.cargo/`
- Python package: `python/pytagmanager/`, `pyproject.toml`
- CLI and public Python API
- Tests: `tests/`, `tests/python/`
- CI and release workflows: `.github/workflows/`
- Documentation, security policy, license, ADR process
- Adjacent PyTagShield workspace at `../PyTagShield` (not a git checkout at
  audit time; no README or published API document)

Executed locally:

| Command | Result |
|---|---|
| `cargo test` | **23 passed** (8 Rust unit + 15 integration) |
| `cargo fmt --check` | **clean** (exit 0) |
| `cargo clippy --all-targets -- -D warnings` | **clean** (exit 0) |
| `.venv-test/bin/python -m pytest tests/python -q` | **419 passed, 4 skipped** in 210.39s |
| `pytagmanager --help` | 8 commands exposed |

Environment notes:

- Python test run used Python **3.12.13**. The project declares
  `requires-python >=3.10`; the repository's own `.venv` is Python 3.9.6 and
  is therefore not a valid reference environment for the declared support
  range.
- The four skipped tests are Ollama-dependent
  (`test_intent_ollama.py` ×3, `test_sitewide_page_type.py` ×1); they skip
  because no Ollama server is running. This is expected, not a failure.
- Browser tests are **real Playwright/Chromium tests**, not mocks. The
  matching Chromium build (`playwright chromium v1223`) had to be installed
  before the suite ran green. Without it, 77 browser-dependent tests fail
  with `Executable doesn't exist` — an environment failure, not a code
  failure.
- No coverage tool is configured, so "419 passed" is a test-count statement,
  not a coverage percentage.

---

## 2. Repository identity and shape

PyTagManager is a **hybrid Rust + Python CLI/library**:

- **Rust core** (`src/`, compiled through PyO3/maturin as `pytagmanager._core`)
  performs crawling and semantic DOM extraction.
- **Python layer** (`python/pytagmanager/`) performs recommendations,
  exports, diagnostics, reporting, and orchestration.
- **External Rust crawler building blocks** come from
  `github.com/Mullassery/MudFish` at tag `rust-v0.1.3`:
  `mudfish-core`, `mudfish-frontier`, `mudfish-fetch`, `mudfish-parser`,
  `mudfish-browser`. PyTagManager still owns sitemap seeding and DOM-graph
  construction.

There is **no database, no server process, no web UI, no authentication
system, and no persistent application state** in the current product. Outputs
are CLI text and JSON files.

### Dependency summary

- Rust: `pyo3 0.29` (`abi3-py39`), `tokio`, `reqwest` (rustls), `scraper`,
  `roxmltree`, `url`, `futures`, MudFish crates.
- Python: `click>=8.0` only, plus optional `diagnostics` extra:
  `playwright`, `pyyaml`, `google-api-python-client`, `google-auth`,
  `google-auth-oauthlib`.
- Packaging: maturin; wheel + sdist built locally for v0.6.0 (macOS arm64
  wheel only in `dist/`).

---

## 3. Capability inventory

Legend: **Implemented** = real code, reachable, covered by tests;
**Partially implemented** = useful subset, with documented gaps;
**Planned/Deferred** = documented but not built; **Unavailable** = not present
at all.

### 3.1 Crawling and URL discovery

**Status: Implemented.**

- Entry points: `pytagmanager crawl` (`python/pytagmanager/cli.py:31`,
  handler at `:126`), `pytagmanager.crawl_site()`
  (`python/pytagmanager/discovery/crawl.py`), Rust `_core.crawl`
  (`src/lib.rs:47`), orchestrator (`src/crawler/orchestrator.rs`).
- Behavior: async crawl with link discovery, XML sitemap seeding,
  robots.txt respect, BFS/frontier dedup, concurrency, max-page cap,
  retry/backoff, per-host circuit breaker, custom headers, optional rate
  limit, and a default-on SSRF guard for the Rust HTTP path.
- Browser modes: `--browser {off,auto,always}` (MudFish `BrowserRenderer`),
  and `--render` (Playwright re-fetch/re-discovery) via
  `crawl_site_rendered()` (`discovery/crawl.py`).
- Structured `crawl_status` (`success`/`throttled`/`blocked`/`challenged`/
  `failed`) and, when rendered, captured network requests and cookies.
- Tests: `tests/crawl_integration.rs` (15), Python
  `test_core_ffi.py`, `test_cli.py`, `test_discovery_crawl_rendered.py`.

### 3.2 Semantic DOM graph

**Status: Implemented.**

- Rust: `src/dom/{parser,graph,selectors}.rs`.
- Each `SemanticNode` exposes `id`, `parent_id`, `tag`, `xpath`,
  `css_selector`, best-effort `stable_selector`, text, ARIA role/label,
  classes, and attributes. `SemanticGraph` exposes `url`, `nodes`,
  `find_by_tag()`.
- Selector priority: `data-testid` → other `data-*` → `aria-label` → `id`.
- `_core.parse_html(html, url)` lets Python feed rendered HTML back through
  the same parser.
- Tests: Rust unit tests in `src/dom/*`, Python `test_core_ffi.py`.

### 3.3 Tracking recommendations / event discovery

**Status: Implemented (rule-based), with optional local LLM classification.**

- `recommend/heuristics.py` (`recommend_for_graph`) detects buttons, links,
  forms and ARIA-role interactive elements; labels business objectives from
  keyword taxonomies; emits `TrackingRecommendation` with event name, trigger
  type, selector + fallbacks, category, business objective, confidence,
  rationale, page URL (`recommend/models.py`).
- Optional `--intent ollama` uses `OllamaIntentClassifier`; falls back to the
  deterministic heuristic if Ollama is unavailable
  (`intent/ollama_classifier.py`).
- `ClaudeIntentClassifier` remains an explicit `NotImplementedError` seam.
- Tests: `test_heuristics.py`, `test_intent_ollama.py`.

### 3.4 Configuration generation and export

**Status: Implemented for seven destinations.**

- Registry: `export/base.py`'s `EXPORTERS` (one entry per destination);
  CLI `--export` choices are generated from it.
- Destinations:
  - GTM container JSON (`export/gtm.py`)
  - GA4 Measurement Protocol-shaped event config (`export/ga4.py`)
  - Segment Tracking Plan (`export/segment.py`)
  - Snowplow self-describing schemas (`export/snowplow.py`)
  - Tealium iQ profile (`export/tealium.py`)
  - RudderStack tracking plan (`export/rudderstack.py`)
  - Adobe Tags (Launch) rules (`export/adobe_tags.py`)
- Shared taxonomy: `export/_taxonomy.py` maps business objectives to canonical
  event keys; the previously documented seven-objective gap was fixed in
  0.3.1 and the current code covers the full taxonomy.
- GTM live comparison: `pytagmanager gtm-plan` (`cli.py:436`,
  `analytics_api/gtm_plan.py`) compares a generated container with a live
  read-only GTM container via `GtmApiClient` (`analytics_api/gtm_client.py`).
- Tests: `test_exporters.py`, `test_gtm_export.py`, `test_gtm_plan.py`.
- **Important boundary:** these are export artifacts. None of them deploys,
  publishes, or mutates a vendor account. `gtm-plan` is read-only.

### 3.5 Real-browser runtime verification and diagnostics

**Status: Implemented.**

- `pytagmanager diagnose` (`cli.py:482`, handler `:611`) drives real
  Playwright Chromium through `ObservationSession`
  (`observability/session.py`) with `observability/agent.js` injected before
  page scripts.
- Captures clicks, form submits, changes, DOM mutations, dataLayer pushes,
  GTM events, network requests (including first-party `/g/collect` and
  `/mp/collect` shapes), route changes, JS errors, consent changes, API calls,
  visibility, and scroll depth.
- Correlates observations into `TrackingJourney` records
  (`correlation/journey.py`) and runs deterministic rules
  (`diagnostics/rules.py`, 11 rules) producing severity + confidence +
  root-cause `Diagnosis` (`diagnostics/models.py`).
- `--trace` emits a formal `InteractionTrace`
  (`diagnostics/trace.py`): finding → interaction → element → timestamp →
  JS/dataLayer/network → storage change.
- `--site-wide` adds template clustering, consistency analysis, anomaly
  detection, runtime event map, health scores, JSON history, regression
  alerts, and optional webhook notification
  (`sitewide/`, `test_notify_backoff.py`).
- Runtime state capture (`observability/state.py`): cookies, localStorage,
  sessionStorage, dataLayer snapshots and before/after diffs; raw values are
  opt-in via `--capture-storage-values`, sensitive-looking keys always
  redacted.
- Optional live GTM/GA4 cross-checks use caller-supplied credentials
  (`analytics_api/gtm_client.py`, `ga4_client.py`); unit tests use injected
  fake API resources, and live verification is credential-gated.
- Tests: `test_correlation.py`, `test_diagnostics_rules.py`,
  `test_observability_*`, `test_diagnose_*`, `test_sitewide_*`,
  `test_interaction_trace.py`, plus real Chromium fixtures under
  `tests/python/fixtures/observability/`.

### 3.6 Website Data Dictionary

**Status: Implemented.**

- `pytagmanager dictionary` (`cli.py:245`, handler `:309`) crawls with a real
  browser and inventories dataLayer fields, cookies, localStorage, and
  sessionStorage: types, example values, presence frequency.
- `--presence-labels` adds Exists/Exposed/Accessible.
- `--purpose-classifier {heuristic,ollama}` classifies cookie/storage purpose
  with evidence + confidence.
- `--compare-to` performs per-field schema drift; `--gtm-config` /
  `--gtm-container` cross-reference GTM consumers and blast radius.
- `--test-candidates` emits regression Test Candidates.
- Tests: `test_dictionary*.py`.

### 3.7 Tag execution intelligence

**Status: Implemented as observation/static analysis, not as a tag manager.**

- `scan-tags` (`cli.py:927`) static code intelligence from rendered HTML:
  GTM containers and 24+ hard-coded vendor signatures
  (`tagexec/static_scan.py`), including delayed containers via before/after
  snapshots.
- `diagnose --detect-duplicate-tags` (`tagexec/duplicates.py`) flags
  duplicate/conflicting implementations only when runtime corroborates.
- `diagnose --detect-server-side-tagging` (`tagexec/server_side.py`) emits
  only hedged (`Likely`/`Possible`) indicators of server-side tagging.
- `diagnose --tag-graph` (`tagexec/graph.py`) assembles an evidence-labeled
  Tag Execution Graph; HTML/SVG rendering is also available.
- **Boundary:** this discovers and reasons about *existing* implementations.
  It does not create, edit, approve, publish, or execute tags.

### 3.8 Runtime rendering, screenshots, sniffing, interactions

**Status: Implemented.**

- `runtime/renderer.py`, `screenshots.py`, `sniffer.py`,
  `interactions.py`; wired through `crawl --render` and
  `crawl_site_rendered()`.
- Tests: `test_runtime_*.py`, `test_cli_render.py`,
  `test_discovery_crawl_rendered.py`.

### 3.9 Test intelligence

**Status: Implemented.**

- `testintel/` generates evidence-backed `TestCandidate`s from diagnoses,
  consistency findings, schema drift, and performance regressions, and
  exports draft Playwright Python/TypeScript specs. Drafts deliberately
  cannot pass unreviewed (`NotImplementedError` / `test.fixme`).
- Tests: `test_testintel_*.py`.

### 3.10 Script performance intelligence

**Status: Implemented.**

- `perf/` measures LCP/CLS/FCP/TBT/INP via `PerformanceObserver`, runs median
  aggregation over repeated loads, builds a real script inventory and
  dependency graph via CDP initiator data, runs isolation experiments
  (script/group/all-non-essential), joins tagging and performance findings,
  persists environment config, detects regressions, and emits Test
  Candidates.
- `pytagmanager perf` (`cli.py:983`) is the entry point.
- Lighthouse ingestion is available as an optional CLI wrapper
  (`cli.py:1164`, `audit/lighthouse.py`); missing Lighthouse raises a clear
  error rather than fabricating scores.
- Tests: `test_perf_*.py`, `test_lighthouse.py`.

### 3.11 Version control / change detection

**Status: Implemented for crawl snapshots.**

- `version_control/snapshot.py` defines `SNAPSHOT_FORMAT_VERSION = 1` and a
  plain JSON snapshot of pages, reduced DOM nodes, and recommendations.
- `pytagmanager diff` compares two snapshots (`cli.py:233`,
  `version_control/diff.py`).
- **Boundary:** this is crawl-surface change detection (pages/elements/
  recommendations), not immutable tag-configuration revision control.

### 3.12 Tag management control plane

**Status: Unavailable.**

No organization/workspace/container/environment/tag/trigger/variable/
destination/revision/publication/audit domain model exists. No persistent
configuration store exists. `TrackingRecommendation` is an observation-derived
recommendation, not an approvable managed tag.

### 3.13 Stable integration identity / PyTagShield synchronization

**Status: Unavailable.**

- Existing IDs are ephemeral or content-derived:
  `TrackingEvent.id` is a fresh `uuid4()` per observation
  (`observability/events.py`); snapshot page identity is URL; recommendation
  identity is `event_name@selector`.
- No integration, container, config-version, destination, or schema-version
  identity exists.
- No registration, config envelope, sync, acknowledgement, reconciliation,
  activation, or rollback exists.
- Adjacent PyTagShield has a real ingest data plane but **no config-sync
  control plane**. See `docs/architecture/pytagshield-integration.md`.

### 3.14 Consent, authorization, tenancy, audit

**Status: Partially implemented only at the observation/redaction level;
control-plane security is unavailable.**

- Payload redaction: `observability/events.py`'s `is_sensitive_key` /
  `redact_payload`, applied to every `TrackingEvent`.
- Cookie/storage value capture is opt-in; sensitive key names are redacted
  even when on.
- Diagnostic rules include PII-pattern detection.
- **Not present:** user authentication, authorization, roles, tenant
  isolation, audit log, server-side consent enforcement in PyTagManager,
  destination allowlists, control-plane rate limits, secret store, or
  arbitrary-expression sandboxing.

---

## 4. Public interfaces

### 4.1 CLI commands

`pytagmanager --help` exposes:

| Command | Purpose |
|---|---|
| `crawl` | Crawl, recommend, optionally export/snapshot/render/simulate |
| `diff` | Compare two crawl snapshots |
| `dictionary` | Website Data Dictionary and schema drift |
| `diagnose` | Real-browser tracking verification and diagnostics |
| `gtm-plan` | Read-only generated-vs-live GTM comparison |
| `scan-tags` | Static GTM/vendor detection |
| `perf` | Script performance measurement and isolation experiments |
| `lighthouse` | Optional Lighthouse audit ingestion |

There are **no** tag-management, container, publishing, integration, or sync
commands today.

### 4.2 Python public API

`python/pytagmanager/__init__.py` exports:

- `crawl_site`
- `recommend_for_graph`
- `TrackingRecommendation`
- `build_gtm_container`, `export_gtm_json`
- `IntentClassifier`, `IntentResult`, `PageContext`,
  `OllamaIntentClassifier`

Everything else is importable by module path but not part of the curated
top-level API. New control-plane APIs will need an explicit public surface and
stability policy.

### 4.3 On-disk formats

- Crawl snapshots: JSON, `format_version = 1`
  (`version_control/snapshot.py`).
- GTM exports: `exportFormatVersion = 2`-shaped container JSON.
- Diagnostic/JSON reports: ad-hoc report dicts assembled in
  `reporting/json_report.py` and CLI handlers.
- Site-wide health history: append-only JSON array.
- Performance history: JSON.
- No schema registry, no migration framework, no config envelope.

---

## 5. Persistence, concurrency, and state

- The product is **stateless between runs** except for files the user asks it
  to write (`-o`, `--save-snapshot`, `--history`, etc.).
- There is no write lock, atomic-write helper, transactional store, or
  concurrency control. Multiple simultaneous writers to the same history file
  are not coordinated.
- `uuid4()` is used for per-observation IDs only; no durable identity.
- Credentials are file paths or environment-level tool configuration; there
  is no secret store.

---

## 6. Security posture (as built)

Implemented / present:

- Rust crawler SSRF guard for loopback/private/link-local/cloud-metadata
  targets; enforced on the Rust HTTP crawl path.
- Denylist-based payload redaction and opt-in storage-value capture.
- Read-only GTM API scope by default (`tagmanager.readonly`).
- Warning in `SECURITY.md` that Playwright-driven commands
  (`--render`, `diagnose`, `dictionary`, `scan-tags`, `perf`) navigate a real
  browser to arbitrary URLs and are **not covered by the Rust SSRF guard**.
- CI has `cargo audit` and `pip-audit --strict` jobs; the current lockfile
  and Python 3.12 environment are reported clean (note: `SECURITY.md` still
  says dependency scanning is not run, which is stale).
- No credentials are committed in tracked files.

Missing / risky for the target platform:

- No control-plane authentication or authorization.
- No tenant isolation.
- No audit trail.
- No destination allowlist or outbound SSRF protection on user-supplied
  webhook URLs (`--alert-webhook` POSTs to any URL).
- No rate limiting/timeouts for control-plane operations.
- No safe template/expression sandbox (none exists yet).
- No secret store; integration credentials have no defined storage model.
- PyTagShield's own outbound webhook destination has no visible SSRF
  allowlist in the audited snapshot (see integration doc).

**Legal/compliance note:** nothing in PyTagManager constitutes a legal
compliance guarantee. Consent and privacy features are engineering controls;
deployments remain responsible for their own obligations.

---

## 7. Test baseline and preservation constraints

Baseline recorded above. Test distribution is broad across recommendations,
exports, diagnostics, site-wide QA, dictionary, runtime, performance,
test-intelligence, and version control. The four skipped tests are
environment-gated (Ollama), not disabled or weakened.

Preservation constraints derived from the audit:

1. Do not replace the MudFish-backed crawler or remove its SSRF guard.
2. Do not replace real Playwright verification with mocked browser behavior.
3. Do not collapse "discovered/observed tracking" into "approved managed
   configuration."
4. Do not change existing exporter output shapes or `EXPORTERS` dispatch
   without explicit approval and regression tests.
5. Do not change existing CLI command names/options or the top-level Python
   exports incompatibly.
6. Do not delete or weaken tests to make a new build pass.
7. Do not make PyTagShield a mandatory dependency of crawl, discovery,
   export, or browser verification.

---

## 8. Documentation drift found during audit

These do not change the code baseline, but future work must not repeat them:

- `ROADMAP_HONEST.md` still claims "40 Rust tests" and "404 Python tests";
  the verified current counts are 23 and 419+4 skipped.
- `ROADMAP_HONEST.md` still describes the seven-objective export-taxonomy gap
  as open; `export/_taxonomy.py` and the 0.3.1 changelog show it fixed.
- `SECURITY.md` says dependency-vulnerability scanning is not run in CI;
  `.github/workflows/ci.yml` contains `cargo audit` and `pip-audit` jobs.
- `docs/ARCHITECTURE.md` describes the crate as owning its own crawler; the
  code delegates fetch/frontier/robots/politeness/circuit-breaking to
  MudFish, while retaining sitemap seeding and DOM-graph building.
- The repository contains a large planning corpus (`docs/VISION.md`,
  `docs/ROADMAP.md`, `ROADMAP_HONEST.md`) whose status claims occasionally
  lag the code. The code and live tests are the authority.

---

## 9. Classification summary

| Area | Classification |
|---|---|
| URL discovery and crawling | Implemented, tested, real network/browser |
| Semantic DOM graph | Implemented, tested |
| Tracking recommendation generation | Implemented, deterministic + optional Ollama |
| Export to GTM/GA4/Segment/Snowplow/Tealium/RudderStack/Adobe Tags | Implemented, tested |
| Live GTM read-only comparison | Implemented, credential-gated for real accounts |
| Runtime browser verification / diagnostics | Implemented, real Chromium, tested |
| Site-wide QA / anomaly / history / webhook | Implemented, tested |
| Data Dictionary / purpose / schema drift | Implemented, tested |
| Static tag/vendor detection and Tag Execution Graph | Implemented as discovery/evidence only |
| Test Candidates / Playwright drafts | Implemented, drafts intentionally non-passing |
| Performance measurement/isolation | Implemented, tested |
| Lighthouse ingestion | Implemented as optional external binary wrapper |
| Crawl snapshot diff | Implemented, format v1 |
| Tag management domain/control plane | **Unavailable** |
| Stable IDs / config revisions / publishing | **Unavailable** |
| Consent-aware managed tag execution | **Unavailable** (observation redaction only) |
| Auth/tenancy/audit/secret store | **Unavailable** |
| PyTagShield live synchronization | **Unavailable**; real data plane exists, control plane absent |
| Reporting/analytics product | Explicitly out of scope |

**Bottom line:** PyTagManager today is a mature discovery, recommendation,
export, and real-browser verification tool. It is **not** yet a tag
management platform. The target work is additive: introduce managed
configuration, stable identity, versioning/publishing, and PyTagShield
synchronization **around** the existing discovery and verification engines
without displacing them.
