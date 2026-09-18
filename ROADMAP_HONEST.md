# PyTagManager — Honest Status

**Current Version:** v0.2.0
**Last Updated:** 2026-09-17

`docs/VISION.md` is the north star, `docs/ARCHITECTURE.md`/`docs/ROADMAP.md` sequence
the work in detail. This file is shorter on purpose: what's built-and-reachable, what's
built-but-not-reachable, what's not built, and what's currently red in CI — so a future
roadmap decision doesn't have to re-derive this from 2,000+ lines of planning docs first.

## 🟢 Built & verified & reachable (real implementation, wired into the CLI, tested)

- **`pytagmanager crawl`** — async Rust crawler (BFS, sitemap.xml, robots.txt) →
  semantic DOM graph → rule-based tracking recommendations → export to 7 platforms
  (GTM/GA4/Segment/Snowplow/Tealium/RudderStack/Adobe Tags) → optional
  `--save-snapshot`.
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
- **40 Rust tests** + **297 Python tests** (2 of which are environment-flaky — see
  below), plus real end-to-end runs against actual headless Chromium in the diagnostics
  path, not mocks.
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
- **Phase 1.9 (Playwright Discovery & Test Intelligence) is 3 of 5 items in**: new
  `testintel/` package generates evidence-backed `TestCandidate`s from existing
  findings (`generate_diagnosis_candidates()` groups journeys sharing a root cause
  across pages into one candidate with an evidence list; `generate_consistency_
  candidates()` reuses Phase 1.8's business-action-naming-drift reports) plus one
  genuinely new detection (`generate_regression_candidates()`, reusing Phase 1.7's
  Data Dictionary schema drift for field-level present→absent regressions). Severity
  is structurally capped at "Requires verification" -- no generator ever emits
  "Confirmed defect", enforced by a dedicated test. Not yet wired into the CLI or
  paired with a Playwright-script exporter (items 4/5).
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

## 🟡 Built but not reachable via the public API/CLI

- **`_core.parse_html()`** (real Rust PyO3 function, well-tested) — intentionally not
  wrapped by any Python-level convenience function yet; it's a documented future hook
  for a Playwright-rendered-HTML path (`docs/ARCHITECTURE.md`), reachable today only as
  `pytagmanager._core.parse_html(html, url)`.

## 🔴 Not built / explicitly deferred

Phase-by-phase, from `docs/ROADMAP.md` (numbers match that file's headings):

- **Phase 1.7 remainder**: "potential GTM usage" enrichment on the Data Dictionary
  and a GTM blast-radius narrative on schema-drift findings (e.g. "existing GTM
  variables/tags may no longer receive price") — both need live GTM config
  cross-referenced against the dictionary/drift, which needs real container
  credentials this environment doesn't have. Everything else in Phase 1.7 (presence
  labeling, schema drift, purpose classification) is shipped as of this pass.
- **Phase 1.9 remainder** (2 of 5 items): `testintel/playwright_export.py` (draft
  Playwright script per candidate, paired with its evidence trail) and CLI wiring
  (`pytagmanager diagnose --site-wide --test-candidates`).
- **Phase 1.95** (script-impact/performance intelligence) — not started.
- **Cloud-LLM intent classification** (`ClaudeIntentClassifier` in `docs/ROADMAP.md`
  Phase 2) — planned, not implemented. Only the local-Ollama and deterministic paths
  exist today.
- **Visual/screenshot grounding, XDM modeling, the enterprise audit engine, and
  non-web platforms** — deliberately deferred, each with a stated reason in
  `docs/ARCHITECTURE.md`, not silently missing.

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

## Where most work is pending, at a glance

Of the roadmap's post-v1 phases, seven are shipped (0, 0.5, 1.5, 1.6, 1.7, 1.8,
1.85) -- 1.7 minus one GTM-config-dependent enrichment (see above) -- Phase 1.9 is
3 of 5 items in (missing only the Playwright export module and CLI wiring), and
Phase 1.95 plus cloud-LLM intent classification and all of the "deliberately
deferred" list in `docs/ARCHITECTURE.md` haven't been
started. The nearest-term real gaps are keeping CI actually exercising new features
as they ship (the diagnostics-extras gap above shipped a whole feature with broken
CI for an unknown period before that pass caught it) and restoring v0.2.0's full
multi-platform PyPI wheel coverage (see below).
