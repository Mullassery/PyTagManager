# PyTagManager — Product Vision & Roadmap

Status: v1 (Phase 0) shipped. This document defines where the product is
going and in what order. It complements `docs/ARCHITECTURE.md`, which
tracks implementation status phase-by-phase; this document is about
sequencing and rationale, not a restatement of the original spec.

## Product Vision

### The problem

Analytics implementation is manual, slow, and adversarial to change.
Every new CTA, form, or page redesign means an analyst re-inspects the
DOM, an engineer re-writes a selector, and a tag manager gets a new rule
that silently breaks the next time a class name changes. At enterprise
scale — hundreds of thousands of pages, dozens of app teams, multiple
tag management platforms — this doesn't scale linearly with headcount,
it scales worse than linearly, because coverage gaps and duplicate/dead
tags compound over time and nobody has a complete picture of what's
actually implemented versus what's actually happening on the site.

### The thesis

Most of what should be tracked can be *discovered*, not specified. A
button that says "Add to Cart" inside a product page doesn't need a
human to tell a system it's a purchase-intent signal — that's inferable
from its text, position, and surrounding structure. The role of the
human should shift from writing tracking rules to **reviewing and
approving AI-generated ones**. That inversion — discovery and inference
first, human judgment as a review gate rather than a bottleneck — is the
product's core bet.

### What "done" looks like, eventually

A user points PyTagManager at a domain (or an app). It crawls/explores
the experience, builds a structural understanding of it, infers what's
worth tracking and why, and hands back a reviewable, exportable tracking
plan — for the web today, and eventually for every customer touchpoint
(mobile, kiosk, desktop) under one canonical event model, so
`purchase_completed` means the same thing and reports the same way no
matter where it fired.

### Who this is for

- **Analysts/marketers** who currently wait on engineering to instrument
  every new campaign landing page or CTA.
- **Engineers** who'd rather review a generated selector than hand-write
  and maintain hundreds of them.
- **Analytics/governance leads** at enterprises who need to know what's
  *actually* tracked versus what's documented, across teams and
  platforms that have drifted out of sync.

### Product principles

These are the filters every roadmap decision below gets run through:

1. **Explainability is not optional.** Every recommendation ships with a
   rationale — which signals fired, why this maps to that business
   objective. A confidence score with no reasoning is not shippable.
2. **Resilience over completeness.** A recommendation with a selector
   that survives a CSS refactor is worth more than ten that don't.
   `data-*`/ARIA-based selectors are preferred structurally, not as an
   afterthought — this is already load-bearing in the v1 selector engine.
3. **Humans approve, they don't author.** The product's job is to make
   the review fast and trustworthy, not to make instrumentation
   fully automatic and unaccountable.
4. **Vertical slices, not layers.** Each phase below ships something a
   user can run end-to-end, the same discipline v1 was built under —
   not a partially-wired layer that only becomes useful once three other
   phases land.
5. **Cost-aware AI.** LLM calls are for judgment (business intent,
   ambiguous cases), not for work a deterministic rule already does
   well. Phase 2 keeps the rule-based heuristics as a candidate
   generator and uses the LLM to classify/rank, not to re-derive
   everything from scratch on every page.

---

## Roadmap

Numbering reflects execution order and dependency, not the original
spec's phase numbers (see the mapping column). **Phase 0 is shipped.**
Everything after is sequenced so each phase is independently useful and
unlocks the next rather than requiring a big-bang integration.

| # | Phase | Status | Size | Builds on | Spec reference |
|---|---|---|---|---|---|
| 0 | Foundation: crawl + DOM graph + rule-based recommendations + GTM export | **Shipped** | — | — | Appendix A, Phases 1, 2, 6 (partial) |
| 1 | Runtime & visual grounding | Planned | L | 0 | Appendix A, Phases 3–4 |
| 2 | AI business intent classification | Planned | M/L | 0, 1 | Appendix A, Phase 5 |
| 3 | Data layer recommendations + multi-platform export | Planned | M | 0, 2 | Appendix A, Phases 6–7 |
| 4 | Adobe XDM & enterprise schema modeling | Planned | M | 3 | Appendix A, Phase 8 |
| 5 | Enterprise audit & governance engine | Planned | L | 3 (needs export formats to compare against) | Appendix A, Phase 9 |
| 6 | Scale, incremental crawling & change detection | Planned | XL | 0 (crawler), 5 (comparisons over time) | Appendix A, Phases 1, 10 |
| 7 | Mobile discovery engines (Android/iOS) | Planned | XL | 2 (intent classification is platform-agnostic by design) | Appendix B, Android/iOS Discovery |
| 8 | Cross-platform canonical event governance | Planned | M | 3, 7 | Appendix B, Cross-Platform Event Governance |
| 9 | Emerging touchpoints (kiosk, desktop, IoT, AR/VR, wearables, voice) | Exploratory | Unsized | 8 | Appendix B, remaining platforms |

**Sizing scale used below:** S / M / L / XL, relative effort assuming a
small (2–3 engineer) team with no other commitments. These are directional
planning inputs, not committed schedule dates — nobody has run the harder
phases yet, so treat L/XL sizes as "this needs its own spike before it gets
a real estimate," not as a promise.

### Phase 0 — Foundation *(shipped)*

Rust crawler (sitemap/robots/BFS/dedup) + semantic DOM graph engine
(selectors, ARIA) + Python rule-based recommendation engine + GTM export
+ CLI. Static HTML only; no LLM calls. This exists to prove the
architecture end-to-end and to give every later phase a real base to
extend rather than a diagram. See `docs/ARCHITECTURE.md` for exact
implementation status.

### Phase 1 — Runtime & Visual Grounding

**Goal:** stop being blind to anything that isn't in the initial HTML
response — modern sites are mostly client-rendered.

- Playwright-driven Python rendering layer; rendered HTML flows back
  through the existing `parse_html()` entry point, so the Rust DOM graph
  engine doesn't need to change.
- Screenshot capture (full-page, above-the-fold, mobile/desktop
  viewports) stored per page.
- Basic runtime interaction simulation — click, hover, scroll — with
  DOM-mutation and network-call observation.
- Sniff existing analytics instrumentation: `dataLayer.push`, `gtag`,
  known analytics endpoints in outgoing requests. This is what makes
  Phase 5 (audit) possible later — you can't find gaps without knowing
  what's already firing.

**Exit criteria:** recommendations are generated for a client-rendered
SPA test page that Phase 0's static crawl produces zero recommendations
for. Screenshots are retrievable per crawled page.

**Deliberately deferred:** full computer-vision element understanding
(hero/pricing-table/carousel detection from pixels). Runtime DOM +
existing-instrumentation sniffing is higher-leverage first; visual
classification is revisited once there's a concrete case the DOM-based
approach can't handle.

**Work breakdown** — size: **L**

1. `python/pytagmanager/runtime/renderer.py` — Playwright wrapper: launch,
   navigate, wait-for-network-idle, return rendered HTML + console/network
   log. (M)
2. Wire rendered HTML through the existing `_core.parse_html(html, url)` —
   no Rust changes needed. Add a `--render` mode to
   `discovery/crawl.py`/the CLI that uses Rust's crawler purely for URL
   discovery (fast, robots/sitemap-aware) and swaps in Playwright for the
   actual per-page fetch when enabled. (M)
3. `runtime/screenshots.py` — full-page/above-fold/mobile/desktop capture,
   filed under an output dir keyed by page id. (S)
4. `runtime/interactions.py` — click/hover/scroll simulation limited to
   the top-N heuristic candidates (bounds cost), diffing DOM state and
   capturing fired network requests per interaction. (L)
5. `runtime/sniffer.py` — intercept requests matching known analytics
   endpoints (GA/gtag, Segment, Adobe, Snowplow collector patterns) and
   read `window.dataLayer` via `page.evaluate`. This is what Phase 5's
   audit engine needs to know what's already firing. (M)
6. Fixture: a small client-rendered test page/app that a static crawl
   produces zero recommendations for, used as the Phase 1 regression test. (S)

### Phase 2 — AI Business Intent Classification

**Goal:** replace keyword heuristics as the ceiling on recommendation
quality, without abandoning them as the floor.

- Implement `ClaudeIntentClassifier` against the existing
  `IntentClassifier` protocol (`python/pytagmanager/intent/base.py`) —
  the interface was designed for this in v1 specifically so this phase
  is a plug-in, not a rewrite.
- Hybrid pipeline: rule-based heuristics generate *candidates* (cheap,
  deterministic, already fast); the LLM classifies/ranks/labels business
  objective and produces the rationale, alternatives-considered, and
  missing-data notes the spec's "AI Explainability" section calls for.
- Confidence calibration against a hand-labeled validation set of real
  pages, not just prompt-engineering by feel.
- Per-page and per-crawl cost tracking, with a configurable ceiling
  (page/element sampling for very large sites rather than classifying
  every node with an LLM call).

**Exit criteria:** classification precision/recall measured against the
labeled validation set beats the Phase 0 rule-based baseline; cost per
page is known and bounded, not open-ended.

**Work breakdown** — size: **M/L**

1. Extract candidate-node discovery out of
   `recommend/heuristics.py:recommend_for_graph` into a reusable
   `recommend/candidates.py` so the rule-based path and the future LLM
   path share one candidate list instead of two divergent
   implementations. (S)
2. Implement `ClaudeIntentClassifier` (currently a `NotImplementedError`
   stub in `intent/base.py`) against the Anthropic SDK, using structured
   tool-use output matching `IntentResult{business_objective, confidence,
   rationale}` plus the spec's alternatives-considered / missing-data
   fields. (M)
3. Batch candidates per page into one LLM call (page title/URL + node
   summaries: tag, text, selector, matched signals) rather than one call
   per element, to keep cost sub-linear in page complexity. (M)
4. `eval/` — a small hand-labeled fixture set + a script scoring
   precision/recall, run as a regression gate before this phase is
   considered done (and again on every future prompt change). (M)
5. Cost tracking: wrap classifier calls with token/cost accounting;
   surface a `--budget` cap (dollars or call count) on the CLI. (S)
6. Fallback path: on classifier error or budget exhaustion, fall back to
   the Phase 0 rule-based recommendation for that node rather than
   dropping it or hard-failing the crawl. (S)

### Phase 3 — Data Layer Recommendations & Multi-Platform Export

**Goal:** a recommendation isn't done at "click this button" — it needs
to say what data should travel with the event, and it needs to reach
more than one platform.

- Data layer parameter recommendations per event (e.g. a `purchase`
  event's `product_id`/`sku`/`price`/`currency`/...), with explicit
  "this data isn't available in the DOM — developers need to expose it"
  flags rather than silently guessing.
- New exporters implementing the existing `Exporter` protocol
  (`python/pytagmanager/export/base.py`): GA4 event config, Segment
  Tracking Plan, Snowplow schema, and a human-readable Markdown
  implementation guide for handoff to engineers who won't touch the
  tool directly.

**Exit criteria:** one recommendation set exports cleanly to GTM + at
least two of {GA4, Segment, Snowplow} with consistent event naming
across formats.

**Work breakdown** — size: **M**

1. Extend `TrackingRecommendation` (or add a companion
   `DataLayerRecommendation`) with a `parameters` list — each field named,
   flagged `available: bool` (False → "developer must expose this"). (S)
2. Extraction pass for JSON-LD/microdata (schema.org Product/Offer, etc.)
   to pre-fill data-layer values (price, SKU) when actually present in
   the page, instead of only ever flagging them missing. (M)
3. `export/naming.py` — shared event-name normalization so `event_name`
   maps consistently across every exporter rather than each one
   reinventing casing/format conventions. (S)
4. New exporters on the existing `Exporter` protocol
   (`export/base.py`): `export/ga4.py`, `export/segment.py`,
   `export/snowplow.py`. (M, roughly S each)
5. `export/markdown.py` — human-readable implementation guide per crawl,
   for handoff to engineers who won't touch the tool directly. (S)
6. CLI: `--export` accepts a comma-separated list to export multiple
   formats in one run. (S)
7. Golden-file tests per exporter against the existing
   `tests/python/fixtures/sample_page.html` fixture. (S)

### Phase 4 — Adobe XDM & Enterprise Schema Modeling

**Goal:** first-class support for Adobe Experience Platform shops, which
skew enterprise and were explicitly named in the source spec.

- XDM-compatible schema and event-type generation: commerce events,
  product-list items, experience events, identity fields, campaign
  fields, commerce/product/cart objects, payment details.
- Adobe Experience Platform Tags (Launch) export.
- Same "flag what's missing" discipline as Phase 3's data layer work.

**Exit criteria:** generated XDM validates against AEP schema-registry
rules for a representative field group (e.g. commerce/purchase).

**Work breakdown** — size: **M**

1. `export/xdm.py` — map canonical event + Phase 3 data-layer fields to
   XDM field groups (commerce, web, experience event, identity). (M)
2. `export/adobe_launch.py` — Adobe Experience Platform Tags export. (M)
3. Bundle a subset of AEP field-group JSON schemas for local validation
   in tests, since CI won't have live AEP registry access. (S)
4. Extend the Phase 3.5 Markdown "missing data" report with XDM-specific
   required-field gaps. (S)

### Phase 5 — Enterprise Audit & Governance Engine

**Goal:** answer "what's actually implemented, and where's the gap"
against real production tag management configs — the highest-leverage
feature for an org that already has *some* tracking and doesn't trust it.

- Importers for existing GTM containers, Adobe Launch, Segment, and
  Snowplow configurations.
- Gap analysis against discovered-and-recommended tracking: missing,
  duplicate, broken-selector, dead, and never-firing events.
- Remediation report output (reuses Phase 3's Markdown exporter
  pattern).

**Exit criteria:** running the audit against a GTM export seeded with
known, deliberate gaps (a broken selector, a dead tag, an unfired
trigger) surfaces all of them.

**Work breakdown** — size: **L**

1. Config importers, each the rough inverse of the matching exporter:
   `audit/importers/gtm.py`, `adobe_launch.py`, `segment.py`,
   `snowplow.py`. (L, roughly M each)
2. `audit/compare.py` — match imported config entries to discovered
   recommendations by selector/event-name, classify into
   missing / duplicate / broken-selector / dead / unfired. (L)
3. Selector-liveness check: re-resolve each imported selector against the
   latest `SemanticGraph`. Worth adding a Rust-side
   `SemanticGraph.matches_selector(selector) -> bool` for this to stay
   fast at enterprise page counts rather than doing it in Python. (M)
4. "Unfired" detection depends on Phase 1's runtime sniffer having
   actually observed the site's live analytics calls — this is why Phase
   5 is sequenced after Phase 1, not before it. (dependency, no new work)
5. `audit/report.py` — remediation report, reusing the Phase 3 Markdown
   exporter pattern. (S)
6. CLI: `pytagmanager audit <url> --import <config-export.json>`. (S)
7. Test fixture: a GTM export seeded with each gap type, asserting the
   audit surfaces all of them. (M)

### Phase 6 — Scale, Incremental Crawling & Change Detection

**Goal:** the difference between a demo and an enterprise tool is
whether it survives contact with a 200,000-page site and stays useful
after the first crawl.

- Resumable, horizontally-scalable crawling: persisted frontier state,
  distributed fetch workers, authenticated session crawling, and
  handling for faceted navigation / pagination / infinite scroll that
  Phase 0's simple BFS doesn't attempt.
- Crawl versioning and diffing: new/removed pages, selector drift,
  added/removed CTAs, new forms, broken tracking — compared against the
  previous crawl, not recomputed from scratch.
- Scheduled re-crawls, so drift is caught continuously instead of
  discovered manually.

**Exit criteria:** a 10,000+ page test site crawls and diffs against its
previous snapshot within a defined time/resource budget, without manual
intervention.

**Work breakdown** — size: **XL** (the largest phase in this roadmap)

1. Swap the in-memory `Frontier` (`src/crawler/frontier.rs`) for a
   pluggable trait with a persisted (SQLite, via `rusqlite`)
   implementation, so a crawl can resume after interruption. (L)
2. Multi-worker fetching: start with single-machine multiprocessing
   partitioning the frontier by URL prefix/hash across multiple `crawl()`
   invocations, before reaching for a distributed queue (Redis/SQS) — the
   simpler option first, upgrade only if it's actually the bottleneck. (L)
3. Authenticated crawling: cookie/header injection into
   `src/crawler/fetcher.rs`'s `Fetcher`, config-driven (pre-supplied
   session cookies or a scripted login step). (M)
4. Faceted-nav/pagination guardrails in the frontier: detect
   parameter-explosion patterns (`?page=`, `?filter=`) and cap crawl depth
   per pattern rather than per-URL, so one filter UI doesn't consume the
   entire page budget. (M)
5. Infinite scroll requires Phase 1's Playwright layer (scroll-and-observe
   for new content) — static BFS can't discover it. (dependency)
6. Crawl snapshot storage: persist each crawl's `Page`/`SemanticGraph` set
   keyed by `crawl_id` + timestamp. (M)
7. `diff/crawl_diff.py` — new/removed pages, per-node selector/text
   changes, added/removed CTA candidates versus the prior snapshot. (L)
8. Scheduling: document a `cron`/CI-triggered re-crawl pattern rather than
   building a bespoke in-product scheduler for this phase. (S)
9. Load-test fixture: a synthetic 10k-page local site generator, with
   assertions on crawl time and memory/resource ceilings. (M)

### Phase 7 — Mobile Discovery Engines (Android & iOS)

**Goal:** the first step outside the browser, validating that the
platform's core abstractions (semantic graph, business-intent
classification, recommendation model) generalize past DOM/HTML.

- Static analysis: Activities/Fragments/Compose graphs (Android),
  View Controllers/SwiftUI hierarchies (iOS) — the mobile equivalent of
  Phase 0's DOM graph.
- Runtime exploration via emulator/simulator automation, reusing the
  interaction-simulation approach built in Phase 1 conceptually (clicks
  → taps, hover → long-press, etc.).
- Platform-specific code generation: Kotlin/Swift analytics wrappers,
  Firebase/Adobe Mobile SDK integration.

**Exit criteria:** end-to-end recommendation-to-generated-wrapper on one
reference Android app and one reference iOS app.

**Note:** this is a materially larger engineering investment than any
prior phase (new static analyzers, emulator orchestration, two new
runtime environments) and is only taken on once Phases 0–3's
abstractions have proven stable enough to extend rather than redesign.

**Work breakdown** — size: **XL**, new tooling ecosystem, highest schedule risk in this roadmap

1. Android static analyzer: Layouts/Navigation Graphs are XML (tractable
   directly); Compose/Kotlin source likely needs a JVM-side helper
   process rather than a pure-Rust parser — Rust's Kotlin/JVM AST tooling
   isn't mature enough to build on. (L)
2. iOS static analyzer: Storyboards/XIBs are XML (tractable directly);
   Swift/SwiftUI source likely needs a Swift-side helper (SourceKit) for
   the same reason. (L)
3. `mobile/` package orchestrating emulator/simulator runtime automation
   — Android via `adb`/UI Automator, iOS via `xcrun simctl`/XCUITest (or
   Appium for both, trading some control for one integration surface
   instead of two). This is realistically a Python-only surface given the
   ecosystem. (XL)
4. Confirm `TrackingRecommendation`/`IntentClassifier` generalize past the
   web — likely needs a `platform` field and a `screen`/`view` concept
   alongside (or instead of) `page_url`. (M)
5. Code generators: `export/android_kotlin.py`, `export/ios_swift.py`
   producing analytics wrapper code calling Firebase/Adobe Mobile SDK. (M)
6. Stand up one reference Android app and one reference iOS app as the
   concrete end-to-end validation target — do not attempt this phase
   against arbitrary third-party apps first. (M)

### Phase 8 — Cross-Platform Canonical Event Governance

**Goal:** the payoff for having done Phase 7 properly — one event model,
many implementations.

- A canonical event registry (e.g. `purchase_completed` defined once,
  with its schema) that web and mobile exports both map into, rather
  than independently reinventing event names per platform.
- Cross-platform consistency auditing, extending Phase 5's audit engine
  to check that the same business event reports consistently everywhere
  it fires.

**Exit criteria:** a single canonical event resolves correctly through
both the web and mobile export paths in a demo, with the audit engine
flagging it if either drifts.

**Work breakdown** — size: **M** (mostly integration of prior phases, not new discovery tech)

1. `governance/registry.py` — canonical event registry (name, schema,
   description); starts as a checked-in JSON/YAML file, not a service. (M)
2. Every exporter (Phase 3's GA4/Segment/Snowplow, Phase 4's XDM, Phase
   7's Kotlin/Swift generators) resolves event naming/parameters through
   the registry instead of inventing them per call site. (M)
3. Extend Phase 5's audit engine to cross-check registry consistency
   across web and mobile exports, not just within one platform. (M)
4. Demo/test: one canonical event (e.g. `purchase_completed`) flowing
   correctly through both a web and a mobile export path. (S)

### Phase 9 — Emerging Touchpoints *(exploratory)*

Kiosk, desktop, IoT, automotive, AR/VR, wearables, voice — per the
universal spec (Appendix B). Kiosk and desktop are the most tractable
next steps (bounded hardware surface, existing runtime-automation
patterns extend more directly); AR/VR, wearables, and voice are
genuinely R&D-stage for this kind of static+runtime discovery approach
and are scoped platform-by-platform only once there's a concrete
reference integration to build against, not speculatively.

**Work breakdown** — unsized; spike-based, not committed work packages

1. Kiosk: reuse the Phase 1 runtime layer; define hardware event hooks
   (barcode/QR scanner, receipt printer, payment terminal) as a
   documented extension point rather than building speculative
   integrations against hardware nobody's confirmed a need for yet.
2. Desktop: accessibility-tree-based discovery (Windows UI Automation,
   macOS Accessibility API) — scope as its own research spike once a
   real desktop-app target exists.
3. IoT / automotive / AR-VR / wearables / voice: no work packages defined
   — each gets scoped only against a concrete reference integration, per
   the roadmap's "vertical slices, not layers" principle.

---

## Success metrics (how we'll know it's working)

- **Recommendation quality:** precision/recall of generated
  recommendations against analyst-labeled ground truth, tracked from
  Phase 2 onward.
- **Selector resilience:** percentage of recommended selectors that
  still resolve correctly after a re-crawl following a real site change
  (Phase 6 makes this measurable, not just designed-for).
- **Time to implementation:** time from "site changes" to "tracking plan
  reviewed and exported," compared to the manual DOM-inspection baseline.
- **Audit coverage:** percentage of deliberately-seeded gaps an audit
  run (Phase 5) actually surfaces.
- **AI cost per page:** LLM spend per page classified, kept bounded and
  visible rather than growing silently with crawl size.

## Risks & how the roadmap accounts for them

- **Crawling politeness/legality:** robots.txt and rate/concurrency
  limits are already load-bearing in Phase 0, not bolted on later;
  Phase 6's scale work extends the same posture rather than replacing it.
- **LLM cost and hallucination:** Phase 2's hybrid design (rules
  generate candidates, LLM classifies) bounds both the cost surface and
  the failure mode — a hallucinated *rationale* is a review-time problem,
  a hallucinated *candidate element* would be worse and is avoided by
  construction.
- **PII/privacy:** the platform recommends event *structure*, not raw
  captured user data; no phase in this roadmap involves storing
  end-user PII, and data layer recommendations (Phase 3) explicitly flag
  fields as "needs developer exposure" rather than scraping them from
  live user sessions.
- **Enterprise scale:** deferred to Phase 6 deliberately rather than
  over-built into Phase 0 — premature distributed-systems complexity
  would have slowed down proving the core recommendation loop works at
  all.
