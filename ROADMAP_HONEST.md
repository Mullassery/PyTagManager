# PyTagManager — Honest Status

**Current Version:** v0.2.1
**Last Updated:** 2026-10-04 (crawl engine migrated onto Mudfish's
fetch/frontier/robots/circuit-breaker building blocks; see the `pytagmanager
crawl` entry below. `docs/VISION.md`/`docs/ARCHITECTURE.md` describe this
crate as having its own bespoke crawler -- that's now only true for the
sitemap-seeding and DOM-graph-building pieces; fetch/scheduling/politeness/
robots/circuit-breaking are Mudfish's, consumed as git dependencies on
`github.com/Mullassery/MudFish`, not reimplemented here.)

`docs/VISION.md` is the north star, `docs/ARCHITECTURE.md`/`docs/ROADMAP.md` sequence
the work in detail. This file is shorter on purpose: what's built-and-reachable, what's
built-but-not-reachable, what's not built, and what's currently red in CI — so a future
roadmap decision doesn't have to re-derive this from 2,000+ lines of planning docs first.

## 🟢 Built & verified & reachable (real implementation, wired into the CLI, tested)

- **`pytagmanager crawl`** — async crawl (priority frontier, sitemap.xml,
  robots.txt, politeness, retry/backoff, per-host circuit breaker, SSRF guard) →
  semantic DOM graph → rule-based tracking recommendations → export to 7 platforms
  (GTM/GA4/Segment/Snowplow/Tealium/RudderStack/Adobe Tags) → optional
  `--save-snapshot`. **2026-10-04: fetch/frontier/robots/politeness/circuit-breaking
  are now Mudfish's (`mudfish-core`/`mudfish-frontier`/`mudfish-fetch`, consumed as
  git dependencies), not a second bespoke implementation** -- the old
  `src/crawler/{fetcher,frontier,robots}.rs` (~750 lines) were deleted; this crate's
  own `src/crawler/orchestrator.rs` now only does sitemap seeding (Mudfish has none)
  and building `SemanticGraph` from each fetched body (Mudfish's own engine discards
  the body after extracting links/metadata, which isn't enough for a DOM graph).
  Each `Page` now also carries a structured `crawl_status`
  ("success"/"throttled"/"blocked"/"challenged"/"failed", from Mudfish's
  `mudfish_fetch::classify_status`+`detect_challenge` heuristics) and, when rendered
  (see `--browser` below), captured `network_requests`/`cookies`. New
  `pytagmanager crawl --browser {off,auto,always}` (default `off`, zero behavior
  change): a lighter-weight per-page render built on Mudfish's new
  `mudfish-browser` (real headless-Chrome/CDP) crate than the existing
  `--render`/Playwright path below -- `auto` only renders pages whose static HTML
  looks like a near-empty client-rendered shell
  (`mudfish_parser::static_html_looks_js_dependent`, a disclosed-imperfect
  heuristic). **Known gap carried over from Mudfish's own `ROADMAP_HONEST.md`:
  the browser-render path does not go through Mudfish's SSRF guard** -- only use
  `--browser auto`/`always` against trusted targets until that's fixed upstream.
  14 new/rewritten Rust integration tests in `tests/crawl_integration.rs` cover this
  migration (including a live `browser_mode=auto` test against a real launched
  Chrome instance proving JS-injected content and a `fetch()` call are both
  captured).
- **`pytagmanager crawl --render`** — Phase 1 (Runtime & Visual Grounding, the
  differently-numbered phase, distinct from the 0.5/1.x track), now fully shipped
  (all 6 items). New `runtime/` package: `renderer.py` re-fetches each discovered
  page through real Chromium and feeds the rendered `page.content()` HTML back
  through the same `_core.parse_html()` the static crawl uses — no Rust changes
  needed. `screenshots.py` captures 4 real PNGs per page (desktop/mobile x
  above-fold/full-page). `sniffer.py` reuses `tagexec.static_scan.
  classify_vendor_url()` (one vendor-signature list for the whole codebase) against
  every outgoing request, plus a real `window.dataLayer` read. `interactions.py`
  clicks/hovers/scrolls the top-N highest-confidence recommended elements (fresh
  browser context per candidate, bounding cost) and reports real DOM-mutation counts
  and newly-fired network requests, with per-candidate error handling so one
  unreachable selector doesn't hide the rest. Verified against the phase's exit
  criteria with a real client-rendered SPA fixture: a static crawl of it recommends
  nothing (the CTA only exists after JS runs); `--render` finds it. **Disclosed
  trade-off**: every page is fetched twice under `--render` (Rust crawler for
  discovery, browser for the actual render) — a Rust-side
  discover-without-fetching-bodies mode was out of scope. **Disclosed, not
  implemented**: mutation counting is a raw `MutationObserver` record count, not
  `observability/agent.js`'s selector-scoped deduplicated event stream (a different,
  narrower question this doesn't need). Deliberately deferred: computer-vision
  element understanding from pixels (hero/pricing-table/carousel detection) — see
  `docs/ARCHITECTURE.md`.
- **`pytagmanager diff`** — crawl-to-crawl change detection (pages, DOM elements,
  recommendations).
- **`pytagmanager dictionary`** — Website Data Dictionary: variable-level inventory
  across dataLayer/cookies/storage (Phase 1.7, shipped). `--presence-labels` adds
  Exists/Exposed/Accessible labeling per variable; `--purpose-classifier
  {heuristic,ollama}` classifies cookie/storage purpose against a fixed taxonomy with
  evidence + confidence; `--compare-to <old.json>` diffs against a previous run for
  per-field schema drift (added/removed fields, type-distribution shifts, possible
  renames). See below for the one piece of Phase 1.7 still missing (GTM
  blast-radius narrative on drift).
- **`pytagmanager diagnose`** — Tracking Observability & Diagnostics: real headless
  Chromium drives the site, correlates interaction → DOM mutation → dataLayer → GTM →
  GA4 → network, and runs 11 deterministic diagnostic rules with confidence labels.
  `--site-wide` adds cross-page template consistency, statistical anomaly detection,
  `--history`/`--alert-webhook` regression tracking. Optional live `GtmApiClient`/
  `Ga4ApiClient` cross-checks against real published config, if you supply credentials.
- **40 Rust tests** + **404 Python tests** (2 of which are environment-flaky — see
  below), plus real end-to-end runs against actual headless Chromium in the diagnostics
  path, not mocks.
- **Phase 1.95 (Script Impact & Performance Intelligence) is fully shipped.** New
  `perf/measure.py` measures real LCP/CLS/FCP/TBT/INP via the standard
  PerformanceObserver API (not CDP tracing/Lighthouse), aggregated over repeated page
  loads (median, never single-run). New `perf/scripts.py` builds a real script
  inventory (URL, domain, first/third-party, CDP-sourced initiator, load mechanism,
  transfer size, network timing, inferred vendor/category) — genuinely needs CDP
  here, unlike item 1, since only CDP exposes "which script triggered this request."
  Per-script CPU execution time and long-task attribution are disclosed as not
  measured (would need CDP's JS Profiler domain, not built yet), not fabricated. New
  `perf/dependency_graph.py` builds script→script relationships from that initiator
  data, with a cycle-safe transitive-closure query (`downstream_of()`). New
  `perf/experiments.py` is the pillar's actual differentiator per VISION.md §16:
  `isolate_script()`/`isolate_group()`/`isolate_all_non_essential()` block a target
  (plus everything downstream) and re-measure against a baseline, reporting *observed
  experimental impact* for that run, never a general causal claim. Groups are a
  disclosed subset of VISION's full list — only what's actually classifiable today.
  `perf/tagging_join.py` joins measured cost with vendor/category (and a Tag
  Execution Graph node, when supplied); `perf/report.py` ranks scripts by cost and
  summarizes per (already-clustered) template; `TestEnvironmentConfig` (real CDP CPU
  throttling, persisted per result) travels with every `PerformanceBaseline`;
  `perf/history.py` mirrors `sitewide/history.py`'s append-and-diff pattern for
  LCP/TBT regression detection, correlating (never claiming causation from) newly-
  introduced scripts; both feed Phase 1.9's `TestCandidate` model directly for
  budget-exceeded and regression findings. `pytagmanager perf <url>
  [--isolate/--isolate-group/--all-off] [--cpu-throttling] [--history]
  [--test-candidates]` wires all of the above together -- verified live: reproduces
  the phase's exit criteria (a deliberately heavy script named with its measured TBT
  delta from a real isolation run).
- **`pytagmanager scan-tags`** — Phase 1.85 item 1 (of 6): static code intelligence.
  Detects GTM containers and 24 hard-coded vendor SDK signatures (GA4, Google Ads,
  Floodlight, Meta Pixel, Adobe Analytics/AEP/Launch, and others) from a page's
  rendered DOM, including ones that load only after a delay (`--wait` + a
  before/after snapshot diff).
- **`pytagmanager diagnose --detect-duplicate-tags`** — Phase 1.85 item 2 (of 6):
  flags duplicate/conflicting tag implementations (multiple GTM containers, GTM +
  a hard-coded analytics-category vendor, a vendor wired in twice), but only as an
  actual finding once a business interaction's network requests corroborate
  duplicate firing at runtime -- static-only candidates are never reported.
- **`pytagmanager diagnose --detect-server-side-tagging`** — Phase 1.85 item 3 (of
  6): hedged server-side GTM/tagging indicators (a first-party request shaped like
  a GA4 Measurement Protocol hit; one interaction fanning out to multiple external
  vendor hosts). Every indicator's confidence is "Likely" or "Possible" -- never
  "Confirmed" -- enforced by a dedicated test that scans every emitted message for
  unhedged language.
- **`pytagmanager diagnose --tag-graph`** — Phase 1.85 items 5+6 (of 6): assembles
  the Tag Execution Graph from items 1-3's outputs (static-scan nodes, Interaction
  Trace steps, duplicate findings, server-side indicators), every edge labeled with
  the five-level evidence vocabulary docs/VISION.md §17 specifies
  (Observed/Inferred/Suspected/Unknown/Not-observed) -- never a stronger claim than
  its source data supports. JSON output only.
- **Phase 1.85 is fully shipped (6 of 6 items).** Item 4's real, scoped gap: an
  SPA navigation (`history.pushState`/`popstate`) reset none of the mutation/
  visibility/scroll-depth observers' dedup caches, so an SPA rebuilding the same
  selector on every route would silently stop reporting real new occurrences of
  that selector after the first route. Fixed in `agent.js`; verified the fix
  matters by reverting it and confirming the regression test actually fails
  without it.
- **Phase 1.9 (Playwright Discovery & Test Intelligence) is fully shipped.** New
  `testintel/` package generates evidence-backed `TestCandidate`s from existing
  findings (`generate_diagnosis_candidates()` groups journeys sharing a root cause
  across pages into one candidate with an evidence list; `generate_consistency_
  candidates()` reuses Phase 1.8's business-action-naming-drift reports) plus one
  genuinely new detection (`generate_regression_candidates()`, reusing Phase 1.7's
  Data Dictionary schema drift for field-level present→absent regressions). Severity
  is structurally capped at "Requires verification" -- no generator ever emits
  "Confirmed defect", enforced by a dedicated test. Each candidate pairs with a
  draft Playwright script (`export_playwright_script()`) that always ends in
  `raise NotImplementedError`, so a draft can never run as a passing test
  unreviewed. Wired into `pytagmanager diagnose [--site-wide] --test-candidates`
  (diagnosis + consistency categories) and `pytagmanager dictionary --compare-to
  --test-candidates` (regression category, since that command is where both
  `DataDictionary` snapshots already live).
- **`pytagmanager crawl --intent ollama`** — swaps the deterministic keyword heuristic
  for `OllamaIntentClassifier` (a local Ollama model, default `qwen2.5:0.5b`), with
  automatic fallback to the heuristic if Ollama isn't reachable. Also exported from
  `pytagmanager/__init__.py` and pluggable directly via
  `recommend_for_graph(graph, classifier=...)`.
- **Phase 1.8 (Automated Browser Behavior & Runtime Event Intelligence) is fully
  shipped**: `pytagmanager diagnose --track-scroll-depth` treats 25/50/75/90/100%
  scroll milestones as first-class interactions (own journeys, own diagnoses);
  `--trace` adds a formalized, drillable Interaction Trace per journey
  (Finding → Interaction → Element → Timestamp → JS/dataLayer/GTM/network → storage
  change); `--site-wide` now includes a Runtime Event Map (interaction ×
  JS/dataLayer/Network/GTM coverage, site-wide); a new `rule_timing_delay` diagnostic
  flags runtime state that changed suspiciously long after the trigger that needed it
  already fired.

## 🔴 Not built / explicitly deferred

Phase-by-phase, from `docs/ROADMAP.md` (numbers match that file's headings):

- **Phase 1.7 remainder**: "potential GTM usage" enrichment on the Data Dictionary
  and a GTM blast-radius narrative on schema-drift findings (e.g. "existing GTM
  variables/tags may no longer receive price") — both need live GTM config
  cross-referenced against the dictionary/drift, which needs real container
  credentials this environment doesn't have. Everything else in Phase 1.7 (presence
  labeling, schema drift, purpose classification) is shipped as of this pass.
- **Cloud-LLM intent classification** (`ClaudeIntentClassifier` in `docs/ROADMAP.md`
  Phase 2) — planned, not implemented. Only the local-Ollama and deterministic paths
  exist today.
- **Computer-vision element understanding** (hero/pricing-table/carousel detection
  from pixels), **XDM modeling, the enterprise audit engine, and non-web
  platforms** — deliberately deferred, each with a stated reason in
  `docs/ARCHITECTURE.md`, not silently missing. (Real per-page screenshot capture
  and client-rendered DOM discovery are no longer on this list — see Phase 1 above.)

## ⚠️ CI/CD — current status

- **PyPI is now current: v0.2.0 was published 2026-09-14** (the entire Tracking
  Observability & Diagnostics / Site-Wide QA / Data Dictionary / runtime-state feature
  set, plus the CLI-wired `OllamaIntentClassifier`) — `pip install pytagmanager` gets
  it. **Platform coverage is narrower than v0.1.3's release**, though: this release
  only has a macOS arm64 wheel + sdist (built locally; Docker wasn't running and no
  `zig` was available for manylinux cross-compilation), vs. v0.1.3's macOS x86_64 +
  arm64 + Linux x86_64 + aarch64 + sdist. Linux and Intel-Mac users get the sdist and
  need a working Rust toolchain to build from source until a proper multi-platform
  release is cut. There's still no publish/release workflow in `.github/workflows/`
  (only `ci.yml`) — this was a manual `maturin build` + `twine upload`, not an
  automated release; the next release should either restore Docker/zig-based
  cross-compilation or add a `maturin-action`-based GitHub release workflow so this
  doesn't have to be redone by hand and platform coverage doesn't silently regress
  again.
- **The v0.2.0 version bump itself was incomplete**: it updated `pyproject.toml` and
  `python/pytagmanager/__init__.py` to `0.2.0` but missed `Cargo.toml`, which stayed at
  `0.1.3` until this pass (fixed here). Since `pyproject.toml`'s `[project].version` is
  static (not `dynamic = ["version"]` from Cargo.toml), the wheel itself would have
  built as `0.2.0` regardless — but the Rust crate's own version being out of sync with
  the package it's compiled into is worth catching before it causes confusion in a
  release changelog or a `cargo` dependency graph.
- **CI was broken on every push since the Tracking Observability & Diagnostics
  feature landed**, until this pass: `ci.yml` never installed the
  `pytagmanager[diagnostics]` extra or a Playwright Chromium binary, so pytest's
  collection phase hit a bare `ModuleNotFoundError: No module named 'yaml'` and
  aborted entirely (6 collection errors, 0 tests run) — not the graceful per-test
  "install pytagmanager[diagnostics]" message the README describes (that promise only
  holds for the CLI's lazy imports inside `dictionary`/`diagnose`, not for pytest's
  top-level test-module imports). Fixed by adding the extras + `playwright install
  --with-deps chromium` install steps to `ci.yml`.
- **`cargo fmt`/`cargo clippy -D warnings` were also failing** on the same commit
  (formatting drift + a `clippy::type_complexity` lint on a nested `Arc<Mutex<...>>`
  type in `tests/support/mod.rs`) — fixed alongside the above.
- **2 Python tests are environment-flaky, not code bugs**: `test_intent_ollama.py`'s
  and `test_sitewide_page_type.py`'s real-Ollama-response tests can fail on a machine
  where something answers on `localhost:11434` but doesn't actually serve the expected
  model, since `_ollama_reachable()`'s check doesn't verify the model itself. CI
  doesn't run Ollama, so this specific flake shouldn't appear there.
- **`dependency-audit` CI job verified for real 2026-09-22 — and it is currently
  RED, on both sub-jobs.** This sandbox has network access after all (confirmed
  against crates.io, pypi.org, github.com); ran the job's exact steps locally
  instead of waiting for a GitHub Actions run:
  - `cargo audit` (against the committed `Cargo.lock`): **3 real vulnerabilities +
    2 warnings.** `pyo3` 0.22.6 — RUSTSEC-2025-0020 (buffer-overflow risk in
    `PyString::from_object`, fixed >=0.24.1) and RUSTSEC-2026-0177 (missing `Sync`
    bound on `PyCFunction::new_closure` closures, fixed >=0.29.0); `rustls` 0.23.43
    (a `reqwest` transitive dep) — RUSTSEC-2026-0285, severity 5.3/medium (TLS 1.3
    handshake messages accepted across encryption-level boundaries, fixed
    >=0.23.45). Plus warnings: `fxhash` 0.2.1 unmaintained, `chacha20` 0.10.1
    yanked. `cargo audit` exits nonzero on any finding.
  - `pip-audit --strict` (replicated the job's exact install steps —
    `click>=8.0 playwright>=1.40 pyyaml>=6.0 google-api-python-client>=2.100
    google-auth>=2.23 google-auth-oauthlib>=1.1` — in a clean venv): **15 known
    vulnerabilities across 7 packages** — `click` 8.1.8 (PYSEC-2026-2132),
    `requests` 2.32.5 (a `google-api-python-client` transitive dep,
    PYSEC-2026-2275), `filelock`/`msgpack` (playwright transitives), and
    `pip`/`setuptools` (the venv's own bootstrap tooling — present because
    `pip-audit` scans the whole environment, not just declared deps). Exit code 1.
  - **Net: this job will fail on its first real GitHub Actions run, on both
    sub-jobs.** Not a flake — reproducible on demand. The `pyo3` fix in
    particular is a major-version bump (0.22 → 0.29) that's a real breaking-change
    migration (PyO3 0.23+ changed several trait/API surfaces this crate uses),
    correctly out of scope for a quick-fix pass; left as a documented, real
    finding rather than force-fit here. A future pass should either remediate
    (bump `pyo3`/`rustls`/the flagged Python packages and re-verify) or, if a
    finding is accepted as a risk, add a scoped `cargo audit --ignore
    RUSTSEC-...`/`pip-audit` allowlist entry with a comment explaining why —
    not leave the job red indefinitely.

## Technical debt

Concrete, file:line findings — not a generic "could be cleaner" list. None of these
block real use; they're disclosed here so a future session can decide whether/when
to spend time on them.

- ~~**`src/crawler/frontier.rs`'s `Frontier::has_capacity()` had a real off-by-one
  that under-fetched crawls, including returning zero pages for `max_pages=1`.**~~
  **Fixed 2026-09-27** (deep code-review pass, not a documented/known issue before
  this): `has_capacity()` used to also require `self.seen.len() < self.max_pages`,
  but `push()` already increments `seen` *before* the BFS loop ever pops and fetches
  the URL -- so pushing the seed URL alone could already put `seen` at `max_pages`,
  and the orchestrator's outer `while frontier.has_capacity()` loop
  (`src/crawler/orchestrator.rs:92`) would exit before ever fetching anything sitting
  in the queue. Concretely verified before the fix: `crawl(url, max_pages=1)` (a
  very plausible "just check the homepage" CLI invocation) returned **zero pages**,
  not one; a 10-page reachable chain with `max_pages=3` returned only 2 pages, not
  3. Fixed by having `has_capacity()` check only queue emptiness (`push()` already
  enforces the cap on insertion, so the queue can never hold more than `max_pages`
  URLs across the crawl's lifetime either way). Regression tests added:
  `src/crawler/frontier.rs`'s `has_capacity_stays_true_until_the_queue_actually_drains`
  (unit-level), and `tests/crawl_integration.rs`'s `max_pages_1_still_fetches_the_seed_page`
  / `max_pages_caps_exactly_when_more_pages_are_reachable` (end-to-end against a mock
  server) -- all three fail against the pre-fix code and pass after. Verified with
  `cargo test` (43/43 passing, up from 40), `cargo fmt --check`, `cargo clippy
  --all-targets -- -D warnings` (clean), and the full Python suite (404/404 passing,
  unaffected -- no Python test relied on the buggy under-fetch behavior). Two
  existing test docstrings (`tests/python/test_core_ffi.py`) that had previously
  noted this as a known, accepted "pre-existing boundary quirk... not a bug" (and
  worked around it with `max_pages=2`) were updated to stop describing since-fixed
  behavior as current.
- **Export-taxonomy gap: 7 of the 21 CTA business objectives added in Phase 1.8
  export as a generic fallback event on every non-GTM platform, silently losing
  the specific business action.** `python/pytagmanager/recommend/heuristics.py`'s
  `_CTA_KEYWORDS` (lines 47-67, added for Phase 1.8 per the inline comment at line
  40) introduced `"Cart Modification"`, `"Wishlist Intent"`, `"Content Discovery"`,
  `"Pagination"`, `"Video Engagement"`, `"Navigation"`, and `"Modal Interaction"` as
  new `business_objective` values. `python/pytagmanager/export/_taxonomy.py`'s
  `CANONICAL_EVENT_MAP` (lines 17-25) was never updated to include any of them, so
  `canonical_event()` falls back to `DEFAULT_CANONICAL_EVENT = "custom_event"` for
  all seven. Every exporter that routes through `canonical_event()` --
  `export/ga4.py`, `export/segment.py`, `export/snowplow.py`, `export/tealium.py`,
  `export/rudderstack.py`, `export/adobe_tags.py` (`export/gtm.py` is unaffected --
  it uses `rec.event_name` directly, not the canonical taxonomy) -- then falls back
  to *that platform's own* generic default (verified by reading each exporter's
  `_DEFAULT_*` spec and confirming none of the seven keys appear in any of the six
  platform-specific spec dicts): GA4 emits `select_content`, Segment emits
  `"Custom Event Triggered"`, Tealium emits the literal string `"custom_event"` as
  the `tealium_event` value. Concretely verified: a `business_objective="Wishlist
  Intent"` recommendation exports to GA4 as `{"name": "select_content", ...}` and to
  Segment as `{"name": "Custom Event Triggered", ...}` -- the specific business
  objective survives only in each exporter's side-channel metadata field
  (`_pytagmanager.businessObjective` / `rules.labels.pytagmanager_business_objective`
  / etc.), not in the actual event name a GTM/GA4/Segment/Tealium/RudderStack/Adobe
  admin would see or build a report/audience/tag-trigger against. Tealium is the
  worst-affected case: since it has no per-canonical-event spec dict at all (just
  `event_name = canonical_event(rec)` directly, `export/tealium.py:35`), a page with
  *both* a wishlist-add and a pagination click would emit **the same** Tealium event
  name (`"custom_event"`) for both, with a single shared Load Rule keyed off it --
  making them indistinguishable at the platform level even though
  `business_objective` differs in the UDO payload. **Not fixed here**: closing this
  gap means deciding a real, platform-documented event name (and, for GA4/Segment/
  Snowplow/RudderStack, a parameter schema) for each of 7 objectives across 6
  platforms -- the same category of judgment call the original exporters required,
  not a mechanical one-line fix, so left as a documented, verified gap rather than
  force-fit.
- **Dependency versions verified against known CVEs 2026-09-22 — real findings,
  not clean** (see the `dependency-audit` CI status above for the full breakdown):
  3 Rust advisories (`pyo3` x2, `rustls`) + 15 Python advisories (mostly
  transitive — `click`, `requests`, `filelock`, `msgpack`, plus `pip`/`setuptools`
  in the audit environment itself). "No known vulnerabilities" is no longer the
  honest claim — it's "known vulnerabilities exist upstream, none remediated yet."
  The `pyo3` fix is a breaking 0.22→0.29 major-version migration, correctly out
  of scope for a quick-fix pass.
- **No Python lint/format tooling wired into CI or `pyproject.toml`** — a
  `.ruff_cache/` directory exists locally (someone has run `ruff` manually, e.g. via
  an editor integration) but there is no `[tool.ruff]` config in `pyproject.toml` and
  no lint/format step in `ci.yml`. Unlike the Rust side (`cargo fmt --check` +
  `cargo clippy -D warnings`, both enforced in CI), Python code has zero automated
  style/lint enforcement — a contributor's formatting is whatever their own editor
  does, with nothing to catch drift. **Checked 2026-09-22 whether adding a CI gate
  was a quick fix**: with default/unconfigured settings, `ruff check python
  tests/python` reports 788 errors (132 auto-fixable) and `black --check python
  tests/python` would reformat 126 of 146 files — this is massive pre-existing
  formatting/lint debt, not a gap a one-line CI addition can close without either
  reformatting the whole tree unreviewed or shipping a CI job that's red on arrival.
  Deliberately not added this pass; a future pass should run `black`/`ruff --fix`
  as its own reviewed commit (or land a deliberately narrow `[tool.ruff]` config
  that only catches new drift) before wiring either into `ci.yml`.
- ~~**`src/lib.rs:41`**: `tokio::runtime::Runtime::new().expect(...)` panicked on
  Tokio runtime creation failure.~~ **Fixed 2026-09-22**: the `crawl()` pyfunction's
  `py.allow_threads` closure already produces a `Result<Vec<Page>, AppError>`, so
  the `.expect()` became `.map_err(|e| AppError::Internal(...))?` — a new
  `AppError::Internal(String)` variant (for process-level failures unrelated to any
  particular request/URL) now carries this through PyO3's existing
  `From<AppError> for PyErr` into a catchable Python `RuntimeError` instead of a
  panic.
- ~~**`src/crawler/fetcher.rs:82`**: `reqwest::Client::builder()....build().expect(...)`
  panicked instead of using the enclosing `Result<Self, AppError>`.~~ **Fixed
  2026-09-22**: `Fetcher::build()` already returns `Result<Self, AppError>` for its
  other failure modes two lines above, so this became `.build().map_err(|e|
  AppError::Internal(...))?` — no structural reason remained for the panic. Verified
  with `cargo build`, `cargo test` (40/40 passing), `cargo fmt --check`, and
  `cargo clippy --all-targets -- -D warnings` (clean).
- **`python/pytagmanager/testintel/playwright_export.py:63`**: the generated draft
  Playwright script contains a `# TODO: implement the steps above against a real page
  URL from Evidence.` comment before its mandatory `raise NotImplementedError` — this
  is intentional (it's a template for code the *user* fills in, documented extensively
  in the README/this file's Phase 1.9 section), not undisclosed rot in PyTagManager's
  own codebase. Listed here only so a future search for `TODO` in this repo isn't
  surprised by it.
- **No coverage measurement** (`pytest-cov` or equivalent) is configured — 404 passing
  Python tests is a real, verified count (this pass ran the full suite live), but
  there is no line/branch coverage number backing it, so "well-tested" is a claim
  about test *count* and CI-verified breadth, not a measured coverage percentage.
- **`src/crawler/fetcher.rs:79`'s HTTP `User-Agent` string was stale** (`PyTagManagerBot/0.1`
  pointing at a nonexistent `github.com/pytagmanager` URL, while the crate itself was
  already at `0.2.0` under `github.com/Mullassery/PyTagManager`) — fixed in this pass to
  `PyTagManagerBot/0.2 (+https://github.com/Mullassery/PyTagManager)`. Low-impact (no
  test asserted the old string, and it's sent on every outbound crawl request, so a
  site operator inspecting request logs would have seen a slightly wrong version/URL),
  but it's the kind of small drift worth catching in the same pass as the `Cargo.toml`
  version-drift fix noted above.

## Where most work is pending, at a glance

Every numbered post-v1 phase through Phase 1.95 is now shipped (0, 0.5, 1.5, 1.6,
1.7, 1.8, 1.85, 1.9, 1.95), plus the differently-numbered Phase 1 ("Runtime &
Visual Grounding": rendered-HTML crawling, screenshot capture, analytics sniffing,
bounded interaction simulation) -- 1.7 minus one GTM-config-dependent enrichment,
1.95 minus a small set of individually-disclosed sub-gaps (see above), neither
blocking real use. Only cloud-LLM intent classification and the remainder of the
"deliberately deferred" list in `docs/ARCHITECTURE.md` -- computer-vision element
understanding from pixels, XDM modeling, the enterprise audit engine, and non-web
platforms -- remain unstarted. The nearest-term real gaps are keeping CI actually
exercising new features as they ship (the diagnostics-extras gap above shipped a
whole feature with broken CI for an unknown period before that pass caught it) and
restoring v0.2.0's full multi-platform PyPI wheel coverage (see below).
