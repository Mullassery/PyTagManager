# PyTagManager — Honest Status

**Current Version:** v0.2.0
**Last Updated:** 2026-09-11

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
  across dataLayer/cookies/storage (Phase 1.7, partial — see below for what's not in
  this yet).
- **`pytagmanager diagnose`** — Tracking Observability & Diagnostics: real headless
  Chromium drives the site, correlates interaction → DOM mutation → dataLayer → GTM →
  GA4 → network, and runs 11 deterministic diagnostic rules with confidence labels.
  `--site-wide` adds cross-page template consistency, statistical anomaly detection,
  `--history`/`--alert-webhook` regression tracking. Optional live `GtmApiClient`/
  `Ga4ApiClient` cross-checks against real published config, if you supply credentials.
- **23 Rust tests** + **169 Python tests** (2 of which are environment-flaky — see
  below), plus real end-to-end runs against actual headless Chromium in the diagnostics
  path, not mocks.

## 🟡 Built but not reachable via the public API/CLI

- **`OllamaIntentClassifier`** (`intent/ollama_classifier.py`) — a complete, tested,
  documented `IntentClassifier` implementation backed by a local Ollama model. It is
  **not exported from `pytagmanager/__init__.py`** and **not wired into any CLI
  command** — `crawl` hardcodes the deterministic heuristic (`recommend_for_graph`)
  with no `--intent`/`--classifier` flag to opt into it. The only way to use it today
  is importing `pytagmanager.intent.ollama_classifier.OllamaIntentClassifier` directly
  and writing your own glue code around `crawl_site()`'s output — the README documents
  it with a full code sample, but that sample is not something `pytagmanager crawl`
  itself can do. `OllamaPageTypeClassifier` (a *different*, newer Ollama-backed
  classifier for `--site-wide --semantic-labels` template labeling) **is** wired into
  the CLI — don't confuse the two when reading the README.
- **`_core.parse_html()`** (real Rust PyO3 function, well-tested) — intentionally not
  wrapped by any Python-level convenience function yet; it's a documented future hook
  for a Playwright-rendered-HTML path (`docs/ARCHITECTURE.md`), reachable today only as
  `pytagmanager._core.parse_html(html, url)`.

## 🔴 Not built / explicitly deferred

Phase-by-phase, from `docs/ROADMAP.md` (numbers match that file's headings):

- **Phase 1.7 remainder** (Data Dictionary shipped; Schema Drift did not): presence-
  vs-availability labeling (Exists/Exposed/Accessible), per-field schema-drift
  detection in `version_control/diff.py`, cookie/storage purpose classification, and
  "potential GTM usage" enrichment (needs live GTM config cross-reference).
- **Phase 1.8 remainder** (cross-implementation interaction consistency shipped; four
  of five items did not): broader interactive-element taxonomy (menus/accordions/tabs/
  modals/etc.), scroll-depth investigation, a timing-delay diagnostic rule, a Runtime
  Event Map, and a formalized drillable Interaction Trace.
- **Phase 1.85 onward** (GTM client/server execution graph, Playwright discovery/test
  intelligence, script-impact/performance intelligence) — not started.
- **Cloud-LLM intent classification** (`ClaudeIntentClassifier` in `docs/ROADMAP.md`
  Phase 2) — planned, not implemented. Only the local-Ollama and deterministic paths
  exist today.
- **Visual/screenshot grounding, XDM modeling, the enterprise audit engine, and
  non-web platforms** — deliberately deferred, each with a stated reason in
  `docs/ARCHITECTURE.md`, not silently missing.

## ⚠️ CI/CD — current status

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

Of the roadmap's post-v1 phases, four are shipped (0, 0.5, 1.5, 1.6), two are
partially shipped with the harder half remaining (1.7's schema-drift/purpose
classification, 1.8's four remaining sub-items), and everything from Phase 1.85
onward — plus cloud-LLM intent classification and all of the "deliberately deferred"
list in `docs/ARCHITECTURE.md` — hasn't been started. The nearest-term real gap isn't
a missing phase, though — it's the CLI-reachability gap above (`OllamaIntentClassifier`
built but stranded) and keeping CI actually exercising new features as they ship
(the diagnostics-extras gap above shipped a whole feature with broken CI for an
unknown period before this pass caught it).
