# PyTagManager Architecture & Roadmap

PyTagManager's long-term vision is an AI-native analytics implementation
platform, described in full in Appendix A (web-focused) and Appendix B
(universal cross-platform) below. **v1 implements a small, real vertical
slice of that vision** — everything else is roadmap, not vaporware claimed
as done.

## What's implemented

| Capability | Status | Where |
|---|---|---|
| Website crawling (link/sitemap/robots.txt discovery, BFS, dedup) | **Implemented** | `src/crawler/` (Rust) |
| Semantic DOM graph (static HTML structure, selectors, ARIA) | **Implemented** | `src/dom/` (Rust) |
| Selector resilience (data-testid / data-* / aria-label / id priority) | **Implemented** | `src/dom/selectors.rs` |
| Rule-based tracking recommendations (keyword-driven, deterministic) | **Implemented** | `python/pytagmanager/recommend/heuristics.py` |
| CLI (`pytagmanager crawl ...`, `pytagmanager diff ...`) | **Implemented** | `python/pytagmanager/cli.py` |
| Non-GTM exporters (GA4, Segment, Snowplow, Tealium, RudderStack, Adobe Tags) | **Implemented** | `python/pytagmanager/export/{gtm,ga4,segment,snowplow,tealium,rudderstack,adobe_tags}.py`, registered in `export/base.py`'s `EXPORTERS` |
| Version control / change detection across crawls | **Implemented** | `python/pytagmanager/version_control/{snapshot,diff}.py`, wired into the CLI as `crawl --save-snapshot` / `pytagmanager diff` |
| AI business intent classification (LLM-backed) | **Implemented** (local model via Ollama, not a hosted API — see note below) | `python/pytagmanager/intent/ollama_classifier.py` |
| Tracking Observability & Diagnostics: real-browser interaction/DOM-mutation/dataLayer/SPA-navigation/consent capture | **Implemented** | `python/pytagmanager/observability/{agent.js,session.py,scenario.py}` |
| Tracking Observability: event correlation into per-interaction journeys | **Implemented** | `python/pytagmanager/correlation/journey.py` |
| Tracking Observability: live GTM Management API + GA4 Admin/Data API config & realtime-ingestion cross-check | **Implemented** (requires the caller's own GCP credentials — see note below) | `python/pytagmanager/analytics_api/{gtm_client,ga4_client}.py` |
| Tracking Observability: rule-based diagnostic engine + terminal/JSON reporting | **Implemented** (deterministic, no LLM) | `python/pytagmanager/diagnostics/rules.py`, `python/pytagmanager/reporting/` |
| Site-Wide Tagging QA: fetch/XHR/console-error/visibility observers | **Implemented** | `python/pytagmanager/observability/agent.js` |
| Site-Wide Tagging QA: page-template detection (URL pattern + DOM fingerprint clustering) | **Implemented** (heuristic — see note below) | `python/pytagmanager/sitewide/templates.py` |
| Site-Wide Tagging QA: semantic page-type classification (LLM-backed, optional relabeling of templates) | **Implemented** (local model via Ollama, deterministic URL-keyword fallback) | `python/pytagmanager/sitewide/page_type.py`, `diagnose --site-wide --semantic-labels` |
| Site-Wide Tagging QA: cross-page consistency, tracking matrix, template/site health scoring | **Implemented** | `python/pytagmanager/sitewide/{aggregation,report}.py`, wired into `diagnose --site-wide` |
| Site-Wide Tagging QA: ecommerce parameter validation, duplicate-purchase detection, confidence-labeled diagnoses | **Implemented** | `diagnostics/rules.py`'s `rule_ecommerce_missing_parameters`/`find_duplicate_purchases`, `Diagnosis.confidence` |
| Runtime/client-rendered DOM discovery for *generating new* recommendations (SPA content invisible to the static crawler) | **Deliberately deferred** — see note below | — |
| Statistical anomaly detection across a site-wide crawl (unusual event repetition, GTM/GA4 config drift relative to a template's own norm) | **Implemented** | `python/pytagmanager/sitewide/anomalies.py`, wired into `diagnose --site-wide` |
| Historical tracking-health scores + regression detection + webhook alerting across runs | **Implemented** (recurring invocation itself is left to the caller's cron/CI — see note below) | `python/pytagmanager/sitewide/{history,notify}.py`, `diagnose --site-wide --history ... --alert-webhook ...` |
| Visual understanding (screenshots, computer vision) | **Deliberately deferred** — see note below | — |
| XDM-native event modeling (Adobe) | **Deliberately deferred** — see note below | — |
| Enterprise audit engine (GTM/Adobe/Tealium/Segment/Snowplow import + gap analysis) | **Deliberately deferred** — see note below | — |
| Any non-web platform (Android, iOS, kiosk, desktop, IoT, AR/VR, wearables, voice) | **Deliberately deferred** — see note below | — |

Notably: the DOM graph is built from **static HTML only**. Fields the
original spec calls for that require a real browser renderer — bounding
box, z-index, visibility state, scroll position, shadow DOM, iframe
context — are not derivable from a static parse and are out of scope until
a Python-side Playwright layer (Phase 3/4 in Appendix A) hands rendered
HTML back through `parse_html()`, which is already designed to accept it.

The rule-based recommendation engine's "AI explainability" (every
recommendation carries a `rationale` string naming exactly which signals
fired — text, class, id, aria-label) gives the same *shape* of output the
AI intent classifier produces, so `heuristics.py`'s deterministic engine
and `OllamaIntentClassifier`'s model-backed one are interchangeable from a
caller's perspective — see `pytagmanager.intent.base.IntentClassifier`.

### AI business intent classification: what's actually running

`python/pytagmanager/intent/ollama_classifier.py`'s `OllamaIntentClassifier`
is a real, working `IntentClassifier` implementation backed by a **locally
running Ollama model** (default `qwen2.5:0.5b`), not the Anthropic API —
this development environment has no Anthropic API credentials, and calling
a local open-weights model "Claude" would misrepresent what's running. It
talks to Ollama's HTTP API (`http://localhost:11434`) via the standard
library only, using Ollama's structured-output mode (`format: "json"`) to
get a parseable `{business_objective, confidence, rationale}` classification
constrained to the same taxonomy `heuristics.py` uses. If Ollama isn't
running, isn't serving the requested model, or returns something that
doesn't parse, `classify()` falls back to the deterministic keyword
heuristic (`recommend.heuristics.classify_node_keywords`) rather than
raising, and the returned `rationale` always says which path was taken.

`pytagmanager.intent.base.ClaudeIntentClassifier` is kept as-is (still
raising `NotImplementedError`) as the named seam for a *real* Claude API
integration later, once API credentials are available — it is intentionally
not renamed or repurposed to mean "the Ollama one."

### Tracking Observability & Diagnostics: what's actually running

This is a genuinely working real-browser subsystem, not a stub — it
requires `pip install pytagmanager[diagnostics]` (Playwright, PyYAML,
`google-api-python-client`) and, once, `playwright install chromium`.
Architecture, deliberately separated per stage so no diagnostic logic
leaks into browser instrumentation:

```
observability/agent.js + session.py   -- COLLECTION (browser observes; never diagnoses)
        │  TrackingEvent stream (observability/events.py)
        ▼
correlation/journey.py                -- CORRELATION ("X appears related to Y")
        │  TrackingJourney per interaction
        ▼
diagnostics/rules.py                  -- DIAGNOSIS ("given X+Y+Z, the likely failure is A")
        │  Diagnosis (severity, root_cause, message)
        ▼
reporting/{terminal,json_report}.py   -- REPORTING ("explain A to the user")
```

`analytics_api/{gtm_client,ga4_client}.py` are real, complete
implementations of the GTM Management API v2 and GA4 Admin/Data API
clients (request shaping, response normalization, and the GTM
`customEventFilter` → literal-event-name extraction that
`diagnostics.rules.rule_event_name_mismatch` depends on) — what's
credential-gated is *live* verification against a real account, not the
implementation itself; both clients are unit-tested against injected fake
API resources (`tests/python/test_analytics_api_clients.py`) precisely so
correctness doesn't depend on having those credentials. Without
`--gtm-container`/`--ga4-property` + credentials, `diagnose` still runs
fully on hand-authored scenario expectations (`observability/scenario.py`)
or the crawl's own static recommendations — the live-config cross-check is
additive evidence, not a hard requirement.

The 10 spec-defined diagnostic rules plus an 11th
(`rule_pii_leak`, content-pattern PII detection inspired by ObservePoint's
PII Detection feature — distinct from `events.redact_payload`'s
key-name-based redaction, which runs earlier and unconditionally on every
collected payload) are all deterministic; no LLM is in this path,
matching the spec's own "must work without an LLM" requirement. See
`diagnostics/rules.py`'s `REGISTRY` list to add a new one — same registry
pattern as `export/base.py`'s `EXPORTERS`.

**Auto-discovered expectations use a weaker claim than hand-authored
ones, on purpose.** `observability/scenario.py`'s
`auto_scenario_from_recommendations()` (the default, `--scenario`-less
path) asserts `any_datalayer_event`, not `datalayer_event`: the
recommendation's `event_name` (e.g. `"purchase_intent"`) is a label
`recommend.heuristics` invented for PyTagManager's own taxonomy, not a
prediction of the literal name a real site pushes (almost always
something else, like `"add_to_cart"`). An earlier version of this
asserted an exact-name match here, which meant `rule_event_name_mismatch`
fired on essentially every auto-discovered page on a real site — a bug
caught by `test_diagnose_site_wide_history_detects_regression_and_alerts`
requiring two *genuinely different* health scores between a healthy and a
broken fixture, which surfaced that both were scoring 0. `expected_datalayer_event()`
returns a name only for real (`datalayer_event`-kind) hand-authored
assertions; `expects_any_datalayer_event()` is the weaker "some event
fired" check the rules that must work for both paths
(`rule_missing_datalayer_event`, `rule_js_error_blocking`,
`rule_api_call_without_tracking_event`) use instead.

### Site-Wide Tagging QA: what's actually running

Builds on Tracking Observability without changing its architecture:
`sitewide/templates.py` clusters the pages a `diagnose --site-wide` crawl
visits into templates (URL-pattern generalization, with a DOM-class-
fingerprint similarity merge for pages that share a structure without a
shared URL shape); `sitewide/aggregation.py` regroups the same
`TrackingJourney`/`Diagnosis` objects Phase 0.5 already produces by
template to compute pass/fail rates per event
(`analyze_template_consistency` — the spec's own "51 of 342 product pages
missing `add_to_cart`" example is a direct unit test,
`test_analyze_template_consistency_flags_minority_regression`) and
0–100 health scores (`compute_template_health`/`compute_site_health`);
`sitewide/report.py` renders the tracking matrix. `observability/agent.js`
gained `fetch()`/`XMLHttpRequest` wrapping (source `application_api`,
event type `api_call`) and `console.error`/`unhandledrejection` capture,
both feeding the same `TrackingEvent` stream and `REGISTRY` rule engine
Phase 0.5 already had — no parallel pipeline. `Diagnosis` gained a
`confidence` field (Confirmed/Highly likely/Possible/Needs investigation)
alongside `severity`, so e.g. `rule_js_error_blocking`'s correlation-based
finding is labeled "Possible" rather than presented with the same
certainty as a directly-observed `rule_missing_datalayer_event` ("Confirmed").

Template labels default to a **naming heuristic, not semantic
understanding**: a `/deals` page labeled "Deals" is accurate because
that's literally its URL segment, not because PyTagManager understands
what a deals page is for. `diagnose --site-wide --semantic-labels` adds a
real semantic layer on top, mirroring `intent/ollama_classifier.py`'s
pattern exactly: `sitewide/page_type.py`'s `OllamaPageTypeClassifier`
sends a privacy-conscious summary of a sampled page (title, headings, CTA
text — never full HTML or form values) to a locally running Ollama model,
which picks one of a fixed page-type taxonomy (Homepage/Product/Category/
Cart/Checkout/Confirmation/.../Other); `assign_semantic_labels` relabels
each template by majority vote across a sample of its pages. If Ollama
isn't reachable, `HeuristicPageTypeClassifier`'s URL-keyword matching
(`checkout`, `cart`, `account`, ...) is used instead — same
graceful-degradation shape as `OllamaIntentClassifier`, and `--site-wide`
still works with the original URL-segment labels when `--semantic-labels`
isn't passed at all (default behavior is unchanged).

`sitewide/anomalies.py` adds outlier detection *within* an otherwise-passing
template population, distinct from `analyze_template_consistency`'s
pass/fail-rate regressions: `detect_template_anomalies` flags a page firing
a business event far more than its template's own observed average (never
a hardcoded threshold), and separately flags a page whose GTM container ID
or GA4 measurement ID (parsed from the `gtm.js`/collect request URLs
already captured by the network layer) disagrees with the rest of its
template. Both need at least two data points to compute a norm against —
a single page can't be anomalous relative to itself.

`sitewide/history.py` + `sitewide/notify.py` add the "did this get worse
since last time" question across separate `--site-wide` runs: `--history
PATH` appends the run's overall + per-template scores to a plain JSON
file (same append-and-diff philosophy as
`pytagmanager.version_control.snapshot` — no database) and
`detect_regression` flags a >= `--alert-threshold` point drop (default 5)
at the site or template level versus the *immediately preceding* recorded
run. `--alert-webhook URL` (requires `--history`) POSTs a
`{"text": "..."}` payload to any webhook URL when a regression fires —
that shape is Slack's incoming-webhook format, so it works there with no
Slack-specific SDK, and equally for any generic JSON-accepting endpoint.
What's deliberately not built: the scheduler that decides *when* to run
`diagnose --site-wide --history ...` again — that's the caller's cron/CI,
by design (see "Deliberately deferred" below).

### Deliberately deferred (not built this pass, and why)

These items are genuinely out of scope for this pass — not silently
dropped, but each deferred for a distinct, specific reason:

- **Runtime/client-rendered DOM discovery for *generating new*
  recommendations** — Tracking Observability's browser *verifies* whether
  already-known interactions (from a crawl's static recommendations or a
  hand-authored scenario) behave correctly at runtime; it does not feed
  discovered client-rendered DOM back into `recommend_for_graph()` to find
  *new* trackable elements invisible to the static HTTP-fetch crawler.
  Those are different problems — verification vs. discovery — and only
  the first was in scope here.
- **The scheduler itself** — `diagnose --site-wide --history` records and
  compares scores (see the new subsection below); *triggering* it weekly
  (or on any cadence) is left to the caller's own cron/CI, deliberately.
  PyTagManager is a CLI that runs once and exits; embedding a scheduler
  into it would be the wrong layer for that concern, the same way `git`
  doesn't schedule its own `git fetch`.
- **Visual understanding (screenshots, computer vision)** — this is a
  fundamentally different crawling paradigm (rendered-page/pixel analysis
  vs. the static-HTML DOM graph this project builds today) that would need
  its own rendering pipeline, its own test/validation approach (visual
  regression, not JSON-shape assertions), and a multimodal model — a new
  subsystem, not an extension of the existing one.
- **XDM-native event modeling (Adobe)** — Adobe Experience Platform's XDM
  schema system (identity fields, commerce/product/cart objects, mixins,
  schema registries) is a deep, Adobe-proprietary modeling layer distinct
  from the tag/rule authoring surface `export/adobe_tags.py` targets;
  correctly enterprise-tier and out of scope here.
- **Enterprise audit engine** (importing and gap-analyzing existing
  GTM/Adobe/Tealium/Segment/Snowplow configurations against discovered
  interactions) — this is explicitly named "enterprise" in this doc's own
  Phase 9/Appendix A spec, and is architecturally a different feature
  (import + compare + gap-report) from what this pass built (generate +
  export forward). Building it would mean writing an importer/parser for
  five different platforms' live configuration formats, not just their
  documented export schemas.
- **Non-web platforms** (Android, iOS, kiosk, desktop, IoT, AR/VR,
  wearables, voice) — an entirely different product surface (native app
  instrumentation, hardware peripherals, platform-specific SDKs) with no
  shared code path with the Rust/Python web crawler core; correctly out of
  scope for a web-focused tool.

## Extension points for future work

- **New exporter**: implement `build_<platform>_config(recommendations) ->
  dict` following the pattern in `export/gtm.py` (or any of the newer
  exporters), and register it in `export/base.py`'s `EXPORTERS` dict — the
  CLI's `--export` choice list is generated from that dict, so no CLI
  changes are needed.
- **AI intent classification**: `IntentClassifier` in
  `python/pytagmanager/intent/base.py` now has a real implementation
  (`OllamaIntentClassifier`, see above); a future real Claude API
  integration would fill in `ClaudeIntentClassifier` the same way.
- **Browser rendering for new-recommendation discovery**: Playwright is
  now in the codebase (`observability/session.py`), but only for
  *verifying* already-known interactions. Feeding its rendered HTML back
  through `pytagmanager._core.parse_html(rendered_html, url)` to run
  `recommend_for_graph()` against client-rendered (not just static) DOM —
  finding *new* trackable elements a SPA only renders after JS runs — is
  the remaining half of this extension point.
- **New observer type**: add a listener to `observability/agent.js`
  emitting a new `event_type` (see `observability/events.py`'s
  `EVENT_TYPES`), map it to a stage in
  `correlation/journey.py`'s `_STAGE_BY_EVENT_TYPE` if it represents a new
  correlation stage, and it's automatically available to every
  `diagnostics/rules.py` rule without touching the correlation engine —
  this is how `fetch`/`XHR`/`console`/`IntersectionObserver` observers
  (see "Deliberately deferred" above) would plug in.
- **New diagnostic rule**: add a
  `(TrackingJourney, DiagnosticContext) -> Optional[Diagnosis]` function to
  `diagnostics/rules.py` and register it in `REGISTRY` — same pattern as
  `export/base.py`'s `EXPORTERS`.
- **Other platforms** (mobile/kiosk/desktop/etc.): entirely new discovery
  engines, out of scope for the Rust/Python web core built here.

---

## Appendix A: original web-focused spec (10 phases)

AI-Powered Intelligent Web Tracking Discovery & Tag Generation Platform

### Objective

Build an enterprise-grade AI-powered platform that automatically discovers, classifies, documents, audits, and exports website tracking implementations for modern analytics platforms.

The platform should eliminate the need for marketers or analysts to manually inspect the DOM, identify CSS selectors, write JavaScript triggers, or configure hundreds of tracking rules manually.

Instead of asking a user what should be tracked, the platform should intelligently discover everything that is meaningful on a website and generate production-ready tracking specifications.

The system should be designed to support websites ranging from a few pages to enterprise websites containing hundreds of thousands of pages.

### Core Philosophy

Traditional Tag Managers work like this: Developer builds website → Analyst opens browser → Inspects DOM → Finds CSS Selector → Creates Trigger → Creates Variables → Creates Tags → Publishes.

The proposed system inverts this: Website → AI discovers website → AI understands user intent → AI understands business purpose → AI recommends tracking → User reviews → One-click export.

The human becomes the reviewer rather than the implementer.

### High-Level Architecture

Website → Intelligent Crawler → (DOM Analysis Engine + JavaScript Runtime Engine) → Visual Understanding Engine → AI Intent Classification Engine → Tracking Recommendation Engine → (GTM / Adobe Tags / Segment / Snowplow Export)

### Phase 1 — Intelligent Website Discovery

The crawler should automatically discover every accessible page by combining multiple strategies: internal link crawling, XML sitemap parsing, robots.txt awareness, canonical URL handling, dynamic route discovery, SPA route detection, navigation menu traversal, footer link discovery, search-driven discovery, pagination traversal, faceted navigation handling, infinite scrolling support, authenticated session crawling (when credentials are provided), multi-language site discovery, mobile and desktop rendering, API-discovered routes (where applicable).

Each page should be assigned a unique identifier and revisited incrementally to detect changes over time.

### Phase 2 — Intelligent DOM Understanding

Rather than storing raw HTML, build a semantic graph representation of the page. Each node should include: HTML element type, parent-child relationships, XPath, CSS selector, stable selector candidates, visible text, hidden text, ARIA labels, ARIA roles, accessibility metadata, CSS classes, IDs, custom attributes, data attributes, inline styles, bounding box coordinates, z-index, visibility state, scroll position, shadow DOM relationships, iframe context, dynamic rendering state.

The graph should support semantic queries such as "Find every visible call-to-action button inside the Hero section" rather than merely "Find every `<button>` element."

### Phase 3 — Visual Understanding

Render every page in a real browser and capture full-page, above-the-fold, mobile, tablet, and desktop screenshots. Apply computer vision and multimodal AI to understand hero banners, navigation bars, product grids, pricing tables, promotional banners, popups, sticky elements, modals, carousels, accordions, search interfaces, forms, checkout flows, embedded media, cookie banners, live chat widgets. Correlate visual understanding with DOM structure to identify the true importance of page elements.

### Phase 4 — Runtime Behavior Analysis

Launch the website in a real browser (e.g., Chromium) and observe behavior during simulated user interactions: clicks, hover, keyboard navigation, scrolling, form completion, dropdown selection, search, product selection, filter/sort, checkout simulation, modal interactions, tab navigation, carousel interaction, video playback, file downloads.

Capture: JS event listeners, DOM mutations, network/AJAX/fetch/GraphQL/Beacon requests, existing data layer pushes, cookie creation, local/session storage usage, SPA route transitions, analytics library invocations.

### Phase 5 — AI Business Intent Detection

Infer the business purpose of every interactive element rather than merely identifying its HTML type. Examples: Primary/Secondary CTA, Product Purchase, Add to Cart, Checkout, Wishlist, Search, Newsletter Signup, Contact Form, Quote Request, Book Demo, Trial Signup, Login/Logout, Account Creation, Support Chat, Download PDF, Video Engagement, Product Comparison, Pricing Interaction, Social Sharing, Review Submission, Appointment Booking, Event Registration, Payment, Subscription, Feedback Collection.

Each recommendation should include a confidence score and rationale.

### Phase 6 — Tracking Recommendation Engine

For every identified interaction, generate: event name, trigger type, recommended selector, selector fallback hierarchy, event category, business objective, recommended parameters, custom dimensions, conversion flag, engagement flag, funnel stage, suggested audience impacts, confidence score. Selectors should prioritize resilience, favoring data-* attributes and ARIA labels over brittle positional selectors.

### Phase 7 — AI-Powered Data Layer Recommendations

Recommend a standardized data layer for every interaction (e.g. a `purchase` event with product_id, sku, category, quantity, price, currency, coupon, promotion, campaign, user_type, membership, inventory_status). Map discovered information to business concepts and highlight missing data developers should expose.

### Phase 8 — XDM-Native Event Modeling

Generate Adobe Experience Platform XDM-compatible schemas and mappings: eventType, commerce events, web events, product list items, experience events, identity fields, marketing campaign fields, commerce/product/cart objects, payment details, device information, page metadata. Where data is unavailable, identify required developer additions.

### Phase 9 — Enterprise Audit Engine

Import existing configurations from GTM, Adobe Experience Platform Tags (Launch), Tealium, Segment, Snowplow. Compare discovered interactions against implemented tracking to identify missing events, duplicates, broken selectors, obsolete rules, redundant variables, unused triggers, incorrect mappings, inconsistent naming, coverage gaps, dead tags, events firing multiple times, events never firing. Generate a gap analysis with remediation recommendations.

### Phase 10 — Version Control and Change Detection

Track website evolution over time by comparing crawls: new/removed pages, changed layouts, selector changes, added/removed CTAs, new forms, updated navigation, broken tracking, new JS behaviors. Provide version history and change reports for continuous monitoring.

### Export Formats

GTM (JSON, YAML), Adobe Experience Platform Tags (Launch), Adobe XDM mappings, Adobe Customer Journey Analytics event definitions, GA4 event configurations, Segment Tracking Plans, Snowplow schemas, Tealium iQ profiles, RudderStack, CSV, Excel, Markdown implementation guides, JSON APIs.

### AI Explainability

Every recommendation should answer: Why was this element selected? What business objective does it support? How confident is the AI? Which signals contributed? What alternatives were considered? What data is missing? What are the potential implementation risks?

### Long-Term Vision

An AI-native Analytics Implementation Assistant — "GitHub Copilot for Digital Analytics" — combining web crawling, browser automation, semantic DOM analysis, visual AI, runtime observation, business intent inference, standards-aware event modeling (including XDM), implementation auditing, and multi-platform export, dramatically reducing implementation effort and enabling continuous governance across enterprise-scale digital properties.

---

## Appendix B: universal cross-platform spec

AI-Powered Universal Digital Tracking Discovery & Analytics Platform

### Vision

An enterprise-grade, AI-native analytics implementation platform that automatically discovers, understands, recommends, audits, and generates analytics implementations across every major digital platform — Websites, PWAs, SPAs, Android, iOS, Tablet, Smart TV, Digital Kiosks, POS Systems, Desktop (Windows/macOS/Linux), Embedded IoT Interfaces, Automotive Infotainment, Mixed Reality (AR/VR), Wearables, Voice Interfaces.

The objective is to eliminate manual analytics implementation across all customer touchpoints by allowing AI to discover user journeys, business intent, and meaningful interactions automatically.

### Core Philosophy

Traditional analytics implementations require platform-specific expertise (Website → inspect DOM → write GTM tags; Android → instrument Firebase SDK; iOS → instrument Adobe SDK; Kiosk → custom SDK; Desktop → manual event logging). Instead: Application → AI explores → AI understands workflows → AI understands business intent → AI recommends tracking → Review → One-click export. The platform acts as an autonomous analytics architect.

### Universal Architecture

Digital Experience → (Website/PWA, Mobile Apps, Desktop Apps) → Universal Discovery Engine → (Visual AI, Runtime Analysis, Accessibility Engine) → Business Intent Classification Engine → Analytics Recommendation Engine → (GTM, Adobe Tags, Firebase, Custom SDK, ...).

### Android Discovery Engine

**Static analysis**: Activities, Fragments, Jetpack Compose screens, Navigation Graphs, XML Layouts, resources, view IDs, strings, drawables, Kotlin/Java code, SDK integrations, permissions, intent filters, accessibility labels, Material Design components — building a complete application graph.

**Runtime exploration**: automatically interact with buttons, cards, RecyclerViews, lists, bottom sheets, dialogs, FABs, search, nav drawer, bottom nav, tabs, date pickers, camera, QR scanner, maps, auth, payment, checkout, push notifications, deep links, offline mode. Capture view/fragment/activity transitions, navigation events, network calls, SDK events, local DB changes, SharedPreferences, secure storage, analytics SDK calls.

### iOS Discovery Engine

Support UIKit, SwiftUI, Storyboards, XIBs, Navigation/Tab Controllers, Collection/Table Views, custom views. Analyze view controllers, navigation hierarchy, accessibility identifiers, Swift/Obj-C source, storyboards, Auto Layout, resource bundles, localization. Runtime exploration: swipe, long press, pinch, zoom, scroll, context menus, Face ID, Touch ID, Apple Pay, camera, notifications, share sheets, Siri shortcuts.

### Mobile AI Journey Discovery

Rather than tracking screens individually, discover entire customer journeys (e.g. Home → Search → Product → Checkout → Payment → Success), identifying entry/exit points, conversion funnels, dead ends, rage taps, drop-off screens, frequently repeated actions, navigation loops.

### Gesture Intelligence

Track swipe left/right, pinch, rotate, double tap, long press, multi-touch, zoom, drag, pull-to-refresh; AI determines which gestures represent meaningful business events.

### Kiosk Discovery Engine

Understand large touch screens, touch-only interaction, idle mode, attract loops, auto reset, accessibility mode, session timeout, multi-language switching, barcode/QR scanning, NFC, card readers, printers, cameras, signature pads. Discover flows like Idle → Welcome → Language → Browse → Search → Select Product → Customize → Payment → Receipt → Exit → Reset. Monitor hardware: touch display, barcode scanner, RFID, NFC, receipt printer, camera, microphone, speaker, payment terminal, coin acceptor, cash drawer, weight sensors, thermal printer.

### Accessibility Intelligence

Across every platform, inspect VoiceOver, TalkBack, Switch Control, screen readers, keyboard navigation, high contrast, dynamic font sizes, focus order, semantic labels. Recommend analytics around accessibility usage where appropriate, respecting privacy.

### Business Intent Classification

Classify interactions into business concepts regardless of platform: Product Discovery, Lead Generation, Authentication, Purchase, Cart Management, Appointment Booking, Check-in, Boarding Pass, QR/Barcode Scan, Membership Enrollment, Loyalty Redemption, Donation, Survey Completion, Customer Support, Account Recovery, Feedback, Ticket Purchase, Wayfinding, Content Consumption, Media Playback, Search, Subscription, Kiosk Assistance, Queue Management. Each with confidence score and reasoning.

### Analytics Recommendation Engine

Generate consistent canonical event definitions independent of platform (e.g. `purchase_completed` with order_id, products, revenue, currency, payment_method, customer_type, platform), then map to platform-specific outputs:

- **Web**: GTM Containers, Adobe Tags Rules, Tealium, Segment, Snowplow
- **Android**: Kotlin analytics wrappers, Java SDK integration, Firebase Analytics, Adobe Experience Platform Mobile SDK, Amplitude, Mixpanel, Segment, RudderStack
- **iOS**: Swift analytics wrappers, Obj-C integration, Firebase Analytics, Adobe Experience Platform Mobile SDK, Mixpanel, Segment, Amplitude
- **Kiosk**: Embedded SDK integrations, offline event queues, local storage sync, edge analytics, batch upload configs, session reset logic

### AI Audit Engine

Import existing implementations and compare against discovered behavior to detect missing events, duplicate instrumentation, broken mappings, inconsistent naming, over/under-instrumentation, screens without analytics, untracked buttons, ignored gesture events, funnel gaps, checkout issues, SDK configuration problems, platform inconsistencies.

### Cross-Platform Event Governance

Maintain a canonical event model across all digital touchpoints — the same business event (e.g. `purchase_completed`) originating from web, Android, iOS, or a kiosk should map to a shared event definition and schema while generating platform-specific instrumentation automatically, enabling consistent reporting, customer journey analysis, audience building, and attribution across GA4, Adobe Experience Platform, Adobe Customer Journey Analytics, Firebase, Amplitude, Mixpanel, Segment, and Snowplow.

### Long-Term Vision

The universal AI implementation layer for digital analytics — autonomously discovering user experiences, understanding business intent, generating analytics specifications, auditing existing implementations, and maintaining governance across web, mobile, kiosk, desktop, IoT, and emerging interfaces. An intelligent orchestration and implementation assistant, not a replacement for existing analytics platforms — "GitHub Copilot for Digital Analytics Engineering."
