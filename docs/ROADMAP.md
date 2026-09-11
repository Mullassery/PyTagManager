# PyTagManager — Product Vision & Roadmap

Status: v1 (Phase 0) shipped. This document defines where the product is
going and in what order. It complements `docs/ARCHITECTURE.md`, which
tracks implementation status phase-by-phase; this document is about
sequencing and rationale, not a restatement of the original spec.

**See `docs/VISION.md` for the full north-star framing** — the product is
a Website Tagging Intelligence & Runtime State Discovery Platform, not a
URL crawler. This document's phase table below (Phases 1.6–1.95) is the
sequenced execution plan for that vision's five pillars — runtime state
capture, browser interaction investigation, GTM client/server execution
intelligence (the Tag Execution Graph), Playwright test intelligence, and
script performance intelligence — integrated alongside the already-shipped
work, not replacing it. Every new phase below extends an existing module
(`observability/agent.js`, `diagnostics/rules.py`, `sitewide/`,
`version_control/`) rather than forking a parallel system, per Product
Principle 7 below.

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

**Extended thesis (see `docs/VISION.md`):** static DOM inference alone
answers "what could be tracked." It doesn't answer whether the data a
button's click needs actually exists at the moment GTM needs it, whether
it's the same event shape everywhere that action appears, or what it
costs the page to collect it. That requires *runtime ground truth* —
observed dataLayer/cookie/storage state, observed browser interaction
traces, observed script performance impact — not just structural
inference from HTML. Phases 1.6–1.95 below exist to add that ground
truth as first-class data, on top of the same discovery-first,
human-reviews philosophy — the output is still recommendations and
findings a human approves, never an unaccountable auto-pilot.

### What "done" looks like, eventually

A user points PyTagManager at a domain (or an app). It crawls/explores
the experience, builds a structural *and runtime-state* understanding of
it (what dataLayer/cookies/storage actually expose, when, and to what
tagging effect), interacts with it the way a user would, measures what
that instrumentation costs in page performance, infers what's worth
tracking and why, and hands back a reviewable, exportable tracking
plan plus evidence-backed Playwright test candidates — for the web today,
and eventually for every customer touchpoint (mobile, kiosk, desktop)
under one canonical event model, so `purchase_completed` means the same
thing and reports the same way no matter where it fired.

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
6. **Evidence before inference, always.** Every runtime-state finding,
   interaction trace, test candidate, or performance claim (Phases
   1.6–1.95) must show what was actually observed before it shows a
   conclusion — "Observed / Potential issue / Suspected defect /
   Confirmed defect," never a bare verdict. This is the same discipline
   Phase 0.5's `Diagnosis.confidence` already established; the new
   phases extend it to new evidence types rather than introducing a
   second standard.
7. **Extend the existing observability system; don't fork it.** New
   observer types land in `observability/agent.js`, new rules in
   `diagnostics/rules.py`, new aggregations beside `sitewide/`'s existing
   ones — the same pattern that took Phase 0.5 → 1.5. A phase that would
   require a parallel browser-automation subsystem instead of extending
   this one is a sign the phase is scoped wrong.

---

## Roadmap

Numbering reflects execution order and dependency, not the original
spec's phase numbers (see the mapping column). **Phase 0 is shipped.**
Everything after is sequenced so each phase is independently useful and
unlocks the next rather than requiring a big-bang integration.

| # | Phase | Status | Size | Builds on | Spec reference |
|---|---|---|---|---|---|
| 0 | Foundation: crawl + DOM graph + rule-based recommendations + GTM export | **Shipped** | — | — | Appendix A, Phases 1, 2, 6 (partial) |
| 0.5 | Tracking Observability & Diagnostics (real-browser interaction → dataLayer → GTM → GA4 correlation + rule-based diagnosis) | **Shipped** | — | 0 (reuses `recommend_for_graph` for auto-scenario discovery) | not in original spec; see "Tracking Observability" note below |
| 1 | Runtime & visual grounding | **Partially shipped** (runtime interaction/network verification landed as Phase 0.5; visual/screenshot grounding for *discovering new* recommendations is still planned) | L | 0 | Appendix A, Phases 3–4 |
| 1.5 | Site-Wide Tagging QA & Runtime Observer Audit | **Shipped** | — | 0.5 | not in original spec; see note below |
| 1.6 | Runtime State Capture: cookies, storage & full dataLayer snapshot | **Shipped** | M | 0.5 | `docs/VISION.md` §1, §2, §6 — not in original spec |
| 1.7 | Website Data Dictionary & dataLayer schema drift | **Partially shipped** (aggregation + CLI shipped; presence-vs-availability labeling, schema-drift diffing, and the cookie/storage purpose classifier are still planned) | L | 1.6 | `docs/VISION.md` §3–§7 — not in original spec |
| 1.8 | Automated Browser Behavior & Runtime Event Intelligence (extends 1.5) | **Partially shipped** (broadened interactive-element taxonomy + cross-implementation business-action consistency shipped; scroll-depth investigation, timing-delay rule, Runtime Event Map, and formalized Interaction Trace object still planned) | L | 1.5, 1.6 | `docs/VISION.md` §14 — not in original spec |
| 1.85 | GTM Client/Server Execution Intelligence & Tag Execution Graph | Planned | L | 1.6, 1.8 | `docs/VISION.md` §17 — not in original spec |
| 1.9 | Playwright Discovery & Test Intelligence (Test Candidates) | Planned | M | 1.7, 1.8, 1.85 | `docs/VISION.md` §15 — not in original spec |
| 1.95 | Automated Script Impact & Web Performance Intelligence | Planned | XL | 1.6, 1.8, 1.85 (Tag Execution Graph attributes cost per node) | `docs/VISION.md` §16 — not in original spec |
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

### Phase 0.5 — Tracking Observability & Diagnostics *(shipped)*

Not part of the original 10-phase spec (Appendices A/B) — added because
knowing *what should be tracked* (Phase 0) is only half the problem;
knowing *whether it's actually working right now* is the other half, and
enterprises lose more to silently-broken tracking than to undiscovered
CTAs. Drives a real headless browser (Playwright), observes the full
interaction → DOM mutation → dataLayer → GTM → GA4 → network chain via a
lightweight injected agent, correlates it into per-interaction
`TrackingJourney` records, and runs 11 deterministic rules (10 from the
design spec plus a content-pattern PII scan) to produce a plain-language
root-cause diagnosis — not a raw event log. Optionally cross-checks
against the *live* GTM Management API and GA4 Admin/Data API when the
caller supplies their own credentials. See `docs/ARCHITECTURE.md`'s
"Tracking Observability & Diagnostics: what's actually running" section
for the full architecture and `pytagmanager diagnose --help` / the
README's Tracking Observability section for usage.

Phase 0.5 answers "is *this* interaction tracked correctly"; Phase 1.5
(below) answers "is the *entire site* consistently tracked correctly."

### Phase 1.5 — Site-Wide Tagging QA & Runtime Observer Audit *(shipped)*

**Goal:** extend Phase 0.5 from "diagnose one journey" to "diagnose an
entire site and tell me which failures are isolated pages vs. systemic
template/component regressions" — without changing Phase 0.5's
architecture, only building on top of it.

- **More observer types**, added to the same `observability/agent.js`
  (not a parallel subsystem): `fetch()`/`XMLHttpRequest` interception
  (app-level API calls, source `application_api`, correlated via a new
  `rule_api_call_without_tracking_event` against whether a corresponding
  tracking event followed), `console.error` + `unhandledrejection`
  capture (supplementing the existing `window.onerror` hook), and an
  opt-in `IntersectionObserver`-based visibility watcher
  (`startVisibilityObserver`/`stopVisibilityObserver`) for
  impression/viewability tracking.
- **Page-type/template detection** (`sitewide/templates.py`): clusters
  crawled pages using two signals — URL path pattern (numeric/UUID/slug
  segments generalized to `{param}`) as the primary key, with a
  DOM-class-fingerprint similarity merge for pages that share a structure
  without a shared URL pattern. This is a heuristic, documented as such;
  it groups *likely*-related pages, not a site's authoritative information
  architecture.
- **Cross-page consistency + site-wide tracking matrix**
  (`sitewide/aggregation.py`, `sitewide/report.py`): aggregates
  `TrackingJourney`/`Diagnosis` results across a crawl by template,
  surfaces pass/fail rates per event (the spec's own "51/342 product pages
  missing `add_to_cart`" example is a direct unit test), and renders a
  page/template/site tracking-health matrix with 0–100 health scores.
  Coverage metrics that have no supporting observations (e.g. no consent
  events seen anywhere) report `None`/"N/A", never a fabricated number.
- **Statistical anomaly detection** (`sitewide/anomalies.py`): flags
  outliers *within* an otherwise-healthy template population, distinct
  from the pass/fail regressions above — a page firing an event far more
  than its template's own observed average (e.g. "one page firing 4× the
  template's normal `page_view` count"), and a page whose GTM
  container/GA4 measurement ID disagrees with the rest of its template.
  Both computed relative to what was actually observed on other pages in
  the same template, never a hardcoded threshold.
- **Ecommerce-specific validation** (`rule_ecommerce_missing_parameters`,
  `find_duplicate_purchases`): required-parameter checks per GA4 ecommerce
  event (`transaction_id`/`currency`/`items`/`value`), and a cross-journey
  check for the same `transaction_id` firing `purchase` more than once
  anywhere in a session.
- **Confidence-labeled root cause**: `Diagnosis` now carries a
  `confidence` field (Confirmed/Highly likely/Possible/Needs
  investigation) alongside `severity`, so e.g. a JS-error correlation is
  labeled "Possible" while a directly-observed missing event is
  "Confirmed" — severity says how bad it is, confidence says how sure the
  rule is *why*.

- **Semantic page-type classification** (`sitewide/page_type.py`,
  `--semantic-labels`): relabels templates using a locally running Ollama
  model instead of the URL-segment heuristic, following exactly the
  pattern `intent/ollama_classifier.py` established for element-level
  intent — a fixed page-type taxonomy, a privacy-conscious page summary
  (title/headings/CTA text, never full HTML), and a deterministic
  URL-keyword fallback when Ollama isn't reachable. Off by default; the
  original URL-segment labels are unchanged unless `--semantic-labels` is
  passed.

- **Historical scores + regression alerting** (`sitewide/history.py`,
  `sitewide/notify.py`, `--history`/`--alert-webhook`/`--alert-threshold`):
  appends each `--site-wide` run's overall + per-template scores to a
  plain JSON file (same append-and-diff philosophy as
  `version_control.snapshot`), flags a >= threshold point drop versus the
  immediately preceding recorded run, and optionally POSTs a
  Slack-compatible `{"text": ...}` webhook alert when one fires. This is
  the ObservePoint-inspired "weekly audits; alert on decline" idea from
  the original design, minus the scheduler: `diagnose --site-wide
  --history ...` still runs once and exits, so *triggering* it on a
  cadence is the caller's own cron/CI, not something PyTagManager embeds.

Wired into the CLI as `pytagmanager diagnose <url> --site-wide` (crawls
via the existing `discovery.crawl_site`, incompatible with `--scenario`
since site-wide aggregation needs more than one page). See
`docs/ARCHITECTURE.md`'s Tracking Observability section and the README
for usage.

**Still deferred:** the scheduler that decides *when* to run `diagnose
--site-wide --history ...` again — deliberately the caller's cron/CI, not
something this CLI tool embeds itself.

**Bug fixed during this phase's own testing:** the default (`--scenario`-
less) auto-discovery path was asserting that a clicked element's runtime
dataLayer event must exactly match `recommend.heuristics`'s own invented
label (e.g. `"purchase_intent"`) — a label real sites never literally
push — so `rule_event_name_mismatch` fired on essentially every
auto-discovered page. A history-based regression test requiring two
*genuinely different* scores between a healthy and a broken fixture page
surfaced that both scored 0. Fixed by having auto-derived expectations
assert only "some dataLayer event fired," not a specific name; hand-
authored `--scenario` expectations are unaffected (see
`docs/ARCHITECTURE.md` for the detailed before/after).

### Phase 1.6 — Runtime State Capture: Cookies, Storage & Full DataLayer Snapshot *(shipped)*

**Goal:** close the confirmed zero-to-one gap `docs/VISION.md` is built
on — cookies, localStorage, and sessionStorage are not captured *anywhere*
in the codebase today (verified by search), and `dataLayer` capture today
only sees `.push()` *events*, not a snapshot of the object's actual
contents. Without this, neither the Data Dictionary (1.7) nor a real
Interaction Trace (1.8) has real data to work with.

- Extend `observability/agent.js` (same file Phase 1.5's observers live
  in, not a new subsystem) with a state-snapshot function reading
  `document.cookie`, `localStorage`, `sessionStorage`, and the full
  `window.dataLayer` array — exposed through the same bridge pattern the
  existing `dataLayer.push` wrap uses.
- `session.py` captures one snapshot at page load and one before/after
  each scenario step, diffing to surface new/removed/modified keys per
  interaction — this before/after diff is what §2's Interaction Trace and
  §14's cross-implementation consistency check consume in Phase 1.8.
- **Privacy discipline (non-negotiable):** this phase's own data — full
  cookie/localStorage *values* — is exactly the kind of thing the
  "Risks & how the roadmap accounts for them" section below already
  commits to never doing ("no phase in this roadmap involves storing
  end-user PII"). Default to capturing **keys + inferred type/shape**
  only; capturing raw *values* is opt-in (`--capture-values`), and when
  on, run the existing PII content-pattern scanner
  (`diagnostics/rules.py`'s pattern detection) over captured values before
  they reach a report, the same way it already gates dataLayer payload
  content today.

**Exit criteria:** `pytagmanager diagnose <url>` reports cookie/
localStorage/sessionStorage/dataLayer state per page, and a before/after
diff for every scenario step, in both the terminal and `--format json`
reports. **Met** — verified live against a fixture page: a click handler
setting a cookie, changing a localStorage value's type, adding a
sessionStorage key, and pushing a dataLayer event all showed up correctly
labeled (`+`/`~`) in both output formats.

**Work breakdown** — size: **M** — shipped as built, one deliberate
deviation from the original plan noted below.

1. `observability/agent.js`: state-snapshot capture function + bridge
   (`window.__ptm.captureState()`), called via `page.evaluate()` rather
   than the streamed-event channel, since a snapshot is a point-in-time
   read, not an event. ✅
2. `session.py`: snapshot-at-load and snapshot-around-each-step wiring
   (`capture_state()`, `state_snapshots`/`state_diffs` properties). ✅
   Cookies are captured via Playwright's CDP-backed
   `BrowserContext.cookies()`, *not* `document.cookie` in `agent.js` —
   the former sees `HttpOnly` cookies, the latter structurally can't. ✅
3. `observability/state.py`: `RuntimeStateSnapshot`/`StorageEntry`/
   `StateDiff` + `diff_state_snapshots()`. ✅
4. Privacy gate on `--capture-storage-values` (named for what it actually
   gates — storage/cookie values specifically, not "capture-values"
   generically), off by default. **Deviation from plan:** redaction is
   key-name-based (`events.is_sensitive_key`, extended with `session`/
   `csrf` markers) rather than routed through the content-pattern PII
   scanner in `diagnostics/rules.py`. For structured key→value data where
   the sensitivity signal *is* the key name (`session_id`, `csrf_token`),
   this is a better fit than a scanner built to find PII patterns inside
   free-text payload content — the two are complementary, not redundant;
   revisit if a cookie/storage value itself needs content-pattern
   scanning (e.g. a value that happens to contain an embedded credential
   under an innocuous key name). ✅ (with above adjustment)
5. Wired into `reporting/{terminal,json_report}.py` as a "RUNTIME STATE
   CHANGES" section / `runtime_state_diffs` JSON key. ✅

**Tests:** 11 new tests in `tests/python/test_observability_state.py`
(unit: diffing logic, redaction; integration: real Chromium against a new
`tests/python/fixtures/observability/runtime_state.html` fixture) — all
passing, no mocked browser behavior.

### Phase 1.7 — Website Data Dictionary & DataLayer Schema Drift *(partially shipped)*

**Goal:** aggregate Phase 1.6's per-page runtime-state snapshots across a
`--site-wide` crawl into the variable-level inventory `docs/VISION.md`
§3–§7 describes, and detect when a dataLayer field's shape drifts between
crawls.

- **Data Dictionary** (`dictionary/build.py`): per variable — every
  observed source path (`dataLayer.user.customer_id` vs.
  `cookie.customer_id` vs. `localStorage.customerId`), type, example
  values, observed frequency, which pages have/lack it, first/last
  observed, and potential GTM usage. Built from Phase 1.6's snapshots
  the same way `sitewide/aggregation.py` already builds a tracking matrix
  from `TrackingJourney`s — reuse that aggregation pattern, don't invent
  a second one.
- **Presence vs. availability labeling** (§4): Exists / Exposed /
  Accessible / Available-at-trigger-time / Consistently-populated. The
  last two need Phase 1.8's interaction timing data; ship the first three
  (page-load-time signals only) first as an independently useful slice,
  add the timing-dependent two once 1.8 lands.
- **DataLayer schema drift detection** (§5): extend
  `version_control/diff.py`'s existing crawl-to-crawl diffing down to the
  per-event-field level (new/removed/renamed keys, type changes, value
  distribution shifts like "`transaction_id`: 96% string, 4% number").
- **Cookie/storage purpose classification** (§6): fixed taxonomy
  (identity/auth/consent/attribution/campaign/experiment/cart/
  preferences/session/personalization/analytics/advertising), evidence
  collected deterministically first (created-after-campaign-param,
  persists-across-pages, consumed-by-an-analytics-request), an optional
  Ollama-backed classifier ranks/labels *from that evidence* — same
  cost-aware-AI split as Phase 2, same fallback-to-deterministic pattern
  as `intent/ollama_classifier.py` and `sitewide/page_type.py`. Every
  classification carries confidence + the evidence list, never a bare
  label.

**Exit criteria:** a fixture site with a deliberately-renamed dataLayer
field (`dataLayer.product.price` → `dataLayer.product.pricing.amount`)
between two snapshots is flagged as a breaking schema change, naming the
downstream blast radius ("existing GTM variables/tags may no longer
receive price").

**Work breakdown** — size: **L**

1. `dictionary/build.py` — Data Dictionary aggregation. **Shipped**:
   `build_data_dictionary()` aggregates cookies/localStorage/
   sessionStorage keys and dataLayer event names/fields across however
   many `RuntimeStateSnapshot`s it's given (one page or a whole crawl),
   tracking per-variable `value_types`, `pages_present`,
   `presence_ratio`, and first/last-observed timestamps. Deliberately one
   level deep for dataLayer fields (`event_name.field`) — a full recursive
   flatten of nested shapes like `ecommerce.items[]` is scoped into item 3
   below, not this pass. No "potential GTM usage" field yet — that needs
   live GTM config (Phase 0.5's `GtmApiClient`) cross-referenced against
   the dictionary, not built in this slice. (L)
2. Presence-vs-availability labeling, page-load-signal subset first.
   **Not yet built** — the aggregation above reports raw presence
   (observed/not, on how many pages), not yet the
   Exists/Exposed/Accessible distinction §4 calls for.
3. `version_control/diff.py` extension for per-event-field schema drift.
   **Not yet built.**
4. Cookie/storage purpose classifier (deterministic evidence + optional
   Ollama ranking). **Not yet built.**
5. CLI: `pytagmanager dictionary <url> -o dictionary.json`. **Shipped**
   (as `pytagmanager dictionary`, both `--format text` and `--format
   json`; no separate `--site-wide` flag needed — it always aggregates
   across every page the crawl discovers, one page or many). Verified
   live against a 3-fixture-page crawl: correctly reported `cart_id`
   observed with two different value types (`string` at load, `json_array`
   after an interaction changed it) — exactly the kind of drift signal
   this phase exists to surface. (S)

**Tests:** 8 new tests in `tests/python/test_dictionary.py` (unit:
aggregation/dedup/type-tracking logic; CLI end-to-end via the same
crawl-discovery-substitution pattern `test_diagnose_site_wide_cli.py`
established, since the Rust crawler's SSRF guard correctly refuses the
loopback fixture server).

**Found and fixed during this phase's testing:** a stale, pre-abi3
`_core.cpython-39-darwin.so` build artifact in `python/pytagmanager/`
(untracked, gitignored, dated well before the `abi3-py39` PyO3 feature
was adopted) was shadowing the current `_core.abi3.so` — CPython prefers
the platform-specific suffix over `abi3` when both exist in the same
directory. This silently ran every test against a stale extension
missing the Phase 1.6 rate-limit/header `crawl()` signature, surfacing as
a confusing `TypeError` in an unrelated test. Deleted; not a code change,
a local build-hygiene fix (same class of issue as the PyRoboFrames
editable-install artifact noted elsewhere).

### Phase 1.8 — Automated Browser Behavior & Runtime Event Intelligence *(partially shipped)*

**Goal:** extend Phase 1.5's observer/correlation system with the items
from `docs/VISION.md` §14 that aren't covered by what's already shipped —
broader interactive-element discovery, scroll-depth investigation,
cross-implementation consistency for the *same* business interaction, a
timing-delay diagnostic class, a Runtime Event Map, and a formalized,
drillable Interaction Trace. Not a parallel system: every item below is
an extension point on `observability/agent.js`, `diagnostics/rules.py`,
and `sitewide/`, the same way Phase 1.5 extended Phase 0.5.

- **Broader interactive-element taxonomy**: today's auto-discovery
  (`recommend/heuristics.py` → `observability/scenario.py`'s
  `auto_scenario_from_recommendations`) is CTA/form-focused. Extend to
  hamburger menus, accordions, tabs, dropdowns, pagination, filters/sort,
  modals, video controls, download buttons, and elements that only render
  after scroll.
- **Scroll-depth investigation** as a first-class interaction type, at
  25/50/75/90/100%, checking for scroll/visibility/dataLayer/network
  signals at each depth — a new observer in `agent.js`, distinct from the
  existing `IntersectionObserver`-based per-element impression watcher.
- **Cross-implementation consistency for the same business action**
  (`sitewide/interaction_consistency.py`, new): does "Add to Cart" fire
  the same event shape from the product page, quick-view, search results,
  a recommendation widget, and mobile? Groups `TrackingJourney`s by
  inferred business-action label (`recommend.heuristics`'s
  `business_objective` taxonomy) instead of by page template — a
  genuinely different cut from Phase 1.5's template-consistency checks,
  not a duplicate of them.
- **Timing-delay diagnostic rule** (`diagnostics/rules.py`): a variable
  that becomes available only N ms after the trigger that needed it
  already fired. Needs Phase 1.6's timestamped state snapshots correlated
  against `TrackingJourney` interaction timestamps.
- **Runtime Event Map** (`sitewide/report.py`): one matrix, interaction ×
  {JS, dataLayer, Network, GTM}, site-wide — alongside, not replacing, the
  existing page/template health matrix.
- **Formalized Interaction Trace**: Finding → Interaction → Element →
  Timestamp → JS event → dataLayer event → storage change → network
  request as an explicit, serializable, drillable object. Mostly a
  presentation layer over what `TrackingJourney` + Phase 1.6's diffs
  already carry, not new capture logic.

**Exit criteria:** a fixture site where "Add to Cart" fires a
differently-named event depending on which page triggered it surfaces as
**one** finding ("N implementations of the same business interaction
observed"), not N unrelated per-page diagnoses. **Met** — verified live:
`healthy_tracking.html` (fires `add_to_cart`) and a second fixture pushing
`addToCart` for the same "Add to Cart" button surface as one
"Purchase Intent: 2 implementations fired, 2 different event names"
finding in both `diagnose --site-wide` text and JSON output.

**Work breakdown** — size: **L**

1. Broaden interactive-element candidate taxonomy. **Shipped**:
   `recommend/heuristics.py` gates on ARIA role (`tab`, `menuitem`, `menu`,
   `link`, `checkbox`, `radio`, `switch`, `option`), not just tag name —
   modern component libraries very often implement tabs/menus/accordions
   as a `<div role="...">`, not a native `<button>`/`<a>`. New keyword
   categories added: Cart Modification, Wishlist Intent, Content
   Discovery (filter/sort), Pagination, Video Engagement, Navigation
   (menus), Modal Interaction. Multi-word phrases preferred over risky
   short substrings (e.g. bare "play" would false-positive inside
   "display"). A plain `<div>` with no interactive role still produces
   zero recommendations — broadening to ARIA roles deliberately didn't
   turn every element on the page into a candidate. (L)
2. Scroll-depth observer + diagnostic checks. **Not yet built.**
3. `sitewide/interaction_consistency.py`. **Shipped**:
   `analyze_business_action_consistency()` groups implementations by
   `TrackingRecommendation.business_objective`, joins each to its
   `TrackingJourney` by (page_url, selector) — the same join key
   `find_untested_recommendations` already established — and reports
   `is_consistent` based only on implementations that actually fired
   (silent/untested ones are counted separately via
   `untested_or_silent_count`, deliberately not folded into the naming
   verdict, since "never fired" is already a different existing rule's
   job). Wired into both `render_site_health_report` and
   `build_site_health_json` as an additive optional parameter. (L)
4. Timing-delay rule in `diagnostics/rules.py`. **Not yet built** — needs
   `StateDiff` to carry its snapshots' timestamps (it currently only
   carries before/after *labels*, not the numeric timestamps) and a join
   key linking a `StateDiff` to the `TrackingJourney` it happened
   alongside (today `StateDiff` labels encode the action but not the
   selector) — real scope, deliberately deferred rather than rushed.
5. Runtime Event Map in `sitewide/report.py`. **Not yet built.**
6. Formalize Interaction Trace as a serializable object. **Not yet
   built.**

**Tests:** 7 new tests in `tests/python/test_interaction_consistency.py`
(unit: grouping/join/consistency logic; end-to-end: real `diagnose
--site-wide` run across two real fixture pages, one new
`add_to_cart_variant_naming.html`, proving the naming-inconsistency
finding against real browser-observed events, not synthetic data) + 4 new
tests in `test_heuristics.py` for the broadened taxonomy.

### Phase 1.85 — GTM Client/Server Execution Intelligence & Tag Execution Graph

**Goal:** per `docs/VISION.md` §17 — understand GTM and website
instrumentation as a distributed system (client-side GTM, server-side
GTM, duplicate/conflicting implementations, background scripts that only
activate post-load), unified under one **Tag Execution Graph** that
supersedes §10's narrower "Tagging Dependency Graph" concept. Every edge
in the graph is labeled Observed/Inferred/Suspected/Unknown/Not-observed
— never fabricated, especially for server-side tagging claims, which are
the single easiest place in this whole roadmap to overclaim.

- **Static code intelligence** (`tagexec/static_scan.py`, new): detect
  GTM container snippets (including multiple/duplicate IDs, dynamically-
  injected GTM, GTM gated on consent/interaction/DOM-ready) and
  hard-coded vendor implementations (GA4, Google Ads, Floodlight, Meta
  Pixel, Adobe Analytics/AEP, and other analytics/ads/experimentation/
  personalization/heatmap/chat/payment/video SDKs) from source/loaded JS.
  Feeds nodes into the graph and into Phase 1.95's script inventory —
  implemented once, consumed by both, not duplicated.
- **Duplicate/conflicting implementation detection**
  (`tagexec/duplicates.py`): flags candidates (two GTM containers, GTM +
  a hard-coded equivalent) but only escalates to a finding once *runtime*
  evidence shows duplicate behavior (two equivalent network requests for
  the same interaction) — reuses Phase 1.8's Interaction Trace as the
  runtime evidence source rather than inferring from static code alone.
- **Server-side GTM indicator detection** (`tagexec/server_side.py`):
  first-party collection/proxy endpoints, one browser event fanning out
  to multiple vendor destinations, request-transformation patterns, known
  tagging-endpoint shapes. Every output is hedged
  ("Likely server-side tagging endpoint" / "Server-side relationship not
  confirmed") — this module's own tests should specifically assert it
  never emits an unhedged claim.
- **Background/post-load script observation**: extends Phase 1.6/1.8's
  observers in `agent.js` to keep watching after `DOMContentLoaded`, after
  consent, after scroll, after SPA navigation, after AJAX/lazy-loading,
  after a delayed timer-based init — a script dormant at load can still
  need investigating.
- **The Tag Execution Graph itself** (`tagexec/graph.py`): assembles
  static-scan nodes + Phase 1.8's Interaction Traces + Phase 1.6's
  network/storage observations + server-side indicators into one graph,
  with per-edge evidence labels. This is the artifact Phase 1.95 attaches
  performance cost to (per node/edge) and Phase 1.9 generates duplicate-
  instrumentation and server-side-dependency Test Candidates from.
- **Unified evidence schema**: one finding record (page, interaction,
  timestamp, script, GTM container/tag/trigger, dataLayer event, DOM
  event, network request, endpoint, initiator, server-side indicator,
  confidence, severity) walkable end-to-end — the same object Phase
  1.8's Interaction Trace and Phase 1.95's performance findings both
  populate into, so a finding from either side is inspectable the same
  way.

**Exit criteria:** a fixture site with two GTM containers both forwarding
the same `add_to_cart` event to GA4 produces one "potential duplicate
instrumentation" finding naming both container IDs, the two network
requests, and their payload similarity — not two unrelated findings.

**Work breakdown** — size: **L**

1. `tagexec/static_scan.py` — GTM/vendor static detection. (L)
2. `tagexec/duplicates.py` — duplicate-implementation detection, gated on
   runtime evidence. (M)
3. `tagexec/server_side.py` — hedged server-side tagging indicators. (M)
4. Background/post-load observer extensions in `agent.js`. (M)
5. `tagexec/graph.py` — Tag Execution Graph assembly + per-edge evidence
   labels. (L)
6. Unified finding/evidence schema shared with Phase 1.8/1.95. (S)

### Phase 1.9 — Playwright Discovery & Test Intelligence

**Goal:** per `docs/VISION.md` §15 — turn Phase 1.6–1.8's findings into
evidence-backed **Test Candidates** an engineer reviews before formalizing
as a real Playwright test. Positioned as the discovery layer *above*
Playwright, not a replacement for it: this phase is mostly a
reframing/packaging layer over existing findings, plus one genuinely new
detection (field-level regression).

- `TestCandidate` data model (`testintel/candidates.py`, new module):
  name, category (event existence / payload / data-type / timing /
  consistency / network / storage / consent / regression), observed
  problem, evidence (which pages, how many), suggested verification
  steps. Severity uses the refined
  Observed→Potential-issue→Suspected-defect→Requires-verification→
  Confirmed-defect scale — a refinement of, not a replacement for,
  `Diagnosis.confidence`'s existing scale.
- **Generator**: derive most Test Candidates from existing
  `Diagnosis`/anomaly/consistency findings (Phases 1.5, 1.8) — reframing,
  not a new detection engine, for every category except regression.
- **Regression-category candidates**: extend `version_control/diff.py`
  to diff at the individual event-field level (a specific dataLayer field
  flips present → absent between two crawls) — finer-grained than the
  existing structural page/element diff and `sitewide/history.py`'s
  aggregate score regression.
- **Playwright export** (`testintel/playwright_export.py`): pseudocode or
  a draft script per candidate, always paired with the evidence that
  produced it. Never emit a script without its evidence trail.

**Exit criteria:** diffing two snapshots of a fixture site where a
`purchase` event's `transaction_id` field was removed produces one
regression-category Test Candidate naming the exact field and the two
crawls compared, with suggested Playwright verification steps attached.

**Work breakdown** — size: **M**

1. `testintel/candidates.py` — `TestCandidate` model. (M)
2. Generator over existing Phase 1.5/1.8 findings. (M)
3. Field-level regression diff in `version_control/diff.py`. (M)
4. `testintel/playwright_export.py`. (S)
5. CLI: `pytagmanager diagnose <url> --site-wide --test-candidates`. (S)

### Phase 1.95 — Automated Script Impact & Web Performance Intelligence

**Goal:** per `docs/VISION.md` §16 — combine tagging intelligence with
performance intelligence: script inventory, dependency graph, controlled
isolation experiments, and a tagging-vs-performance trade-off report.
**Confirmed via search: zero existing performance-measurement code** (no
Lighthouse, Web Vitals, CDP profiling, or throttling anywhere in the
repo) — unlike every other phase in this section, this is a genuinely new
subsystem, not an extension of one that already exists. Size accordingly.

- **Measurement engine** (`perf/measure.py`): CDP-level (via Playwright's
  CDP session) LCP/INP/CLS/FCP/TBT/Speed-Index-equivalent metrics, JS
  transfer/parse/execution time, request counts — aggregated over
  repeated runs (median/percentile, never a single run).
- **Script inventory** (`perf/scripts.py`): per script — URL, domain,
  first/third-party, initiator, load mechanism, timing, size, execution
  time, long tasks — from Playwright's network + performance-entry APIs.
- **Dependency graph** (`perf/dependency_graph.py`): script→script
  relationships from initiator chains, so disabling one script's
  downstream effects aren't double-counted or missed in isolation
  experiments.
- **Isolation experiments** (`perf/experiments.py`): block one script,
  one group (analytics/ads/personalization/chat/social/consent/tag-
  management/heatmaps/A-B-testing), or all non-essential scripts via
  Playwright route interception; re-measure against baseline. Report
  *observed experimental impact*, explicitly distinguished from inferred
  causality — same evidence-first discipline as every other phase here.
- **Tagging-vs-performance join**: cross-reference script domains against
  Phase 1.6/1.8's already-known analytics/marketing network-endpoint
  data, so a script's measured cost can be shown alongside what tagging
  capability it provides. Where Phase 1.85's Tag Execution Graph already
  exists, attribute cost to a specific node/edge in that graph (e.g. "GTM
  → Vendor Loader → Advertising SDK → 5 scripts → long task → INP
  degradation") instead of only to an isolated script in the ranking
  below.
- **Script ranking + Web-Vitals attribution** (`perf/report.py`): reuses
  `sitewide/templates.py`'s existing page-type clustering for
  per-template aggregation rather than a new classifier.
- **Controlled test environment**: standardized browser version,
  viewport, CPU/network throttling, cache state, device profile, consent/
  login state, run count — persisted alongside every result.
- **Performance regression detection**: wires into the existing
  `version_control`/`sitewide/history.py` infrastructure rather than a
  parallel history mechanism — a newly-introduced script correlated with
  a TBT/LCP delta between two crawls.
- **Playwright Test Candidate integration**: reuses Phase 1.9's
  `TestCandidate` model for performance-threshold and script-load-order
  candidates (e.g. "verify script does not load before consent").

**Exit criteria:** running against a fixture page with one deliberately
heavy third-party script produces a report naming that script, its
measured TBT/LCP contribution from an isolation run, and — when its
domain matches a known analytics/marketing endpoint — a tagging-vs-
performance trade-off line for it.

**Work breakdown** — size: **XL** (tied with the original Phase 6 as the
largest phases in this roadmap)

1. `perf/measure.py` — CDP-level measurement engine. (L)
2. `perf/scripts.py` — script inventory. (L)
3. `perf/dependency_graph.py`. (M)
4. `perf/experiments.py` — isolation-experiment runner. (L)
5. Tagging-vs-performance join. (M)
6. `perf/report.py` — ranking, Web-Vitals attribution, per-template
   aggregation. (M)
7. Controlled test-environment config, persisted per result. (M)
8. Performance regression detection via existing history infra. (M)
9. Playwright Test Candidate integration (reuses 1.9). (S)
10. CLI: `pytagmanager perf <url> [--isolate <script> |
    --isolate-group <group> | --all-off] -o report.json`. (M)

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

**Work breakdown** — size: **XL** (tied with Phase 1.95 as the largest
phases in this roadmap)

1. Swap the in-memory `Frontier` (`src/crawler/frontier.rs`) for a
   pluggable trait with a persisted (SQLite, via `rusqlite`)
   implementation, so a crawl can resume after interruption. (L)
2. Multi-worker fetching: start with single-machine multiprocessing
   partitioning the frontier by URL prefix/hash across multiple `crawl()`
   invocations, before reaching for a distributed queue (Redis/SQS) — the
   simpler option first, upgrade only if it's actually the bottleneck. (L)
3. Authenticated crawling: cookie/header injection into
   `src/crawler/fetcher.rs`'s `Fetcher`, config-driven (pre-supplied
   session cookies or a scripted login step). **Partially shipped**: the
   `--header`/`Fetcher::build` custom-header path (`crawl --header
   'Cookie: session=...'`) landed ahead of this phase, alongside per-host
   rate limiting with `Retry-After`/backoff handling on 429/503 (neither
   was a prerequisite for the rest of this phase, so they shipped
   independently rather than waiting on Phase 6). Still open: a scripted
   login step. (M → S remaining)
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
