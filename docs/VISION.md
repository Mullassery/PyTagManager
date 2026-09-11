# PyTagManager — North Star Vision

This document is the product's north star: what PyTagManager is *for*,
independent of what's shipped yet. `docs/ARCHITECTURE.md` tracks
implementation status; `docs/ROADMAP.md` sequences the work. This document
answers "why," and every roadmap phase should trace back to a claim made
here.

## The reframe

**Do not think of this product as a URL crawler.** A traditional crawler
models a website as:

```
Website → URLs → HTML → DOM
```

That model is insufficient for tagging. A modern webpage exposes
information through `dataLayer`, cookies, localStorage, sessionStorage,
JS runtime state, DOM attributes, forms, URL parameters, consent state,
network requests, and application state — and that information is what
Google Tag Manager (and every other tag manager) actually consumes:

```
Website State → GTM Variables → GTM Triggers → GTM Tags → Analytics/Ads/Marketing platforms
```

**Core thesis:** a website is not a collection of URLs. It is a dynamic
runtime data environment, and every page is one observation point into
that environment. URL discovery remains necessary — it's how the platform
finds observation points at scale — but it is an *input* to the
intelligence engine, not the product.

## The five questions the product exists to answer

1. **What data exists?** — discovery (dataLayer keys, cookies, storage,
   DOM attributes, JS state).
2. **Where does it exist?** — source mapping (which layer, which exact
   path — `dataLayer.user.customer_id` vs. `cookie.customer_id` vs.
   `localStorage.customerId`).
3. **When does it exist?** — temporal/runtime analysis (available at page
   load? only after login? only after an interaction? only 800ms after
   the trigger that needed it already fired?).
4. **Is it usable by the tagging layer?** — GTM accessibility. Existing in
   JS application state is not the same as being exposed to GTM.
5. **What is missing or broken?** — the actionable output: gaps,
   inconsistencies, timing failures, schema drift.

Every proposed feature gets evaluated against these five questions and
against the north-star statement below. A feature that crawls more URLs
but doesn't improve understanding of runtime state, tagging accessibility,
data quality, or instrumentation completeness is not automatically a core
capability.

## North-star statement

> Understand everything a website exposes to its digital measurement and
> marketing ecosystem — and determine whether that information is
> available, correct, timely, consistent, and usable for tagging.

## Positioning

Not: URL crawler, website scraper, SEO crawler, DOM crawler, GTM debugger,
analytics debugger — those are components, not the product.

Is: a **Website Tagging Intelligence & Runtime State Discovery Platform**.
The differentiator is that it understands the *data environment* behind a
website, not merely the website's pages.

---

## 1. Website Runtime State — the central abstraction

Model a website as layers, each of which the platform observes and
normalizes into one unified model:

```
Website
├── URL / Route Layer
├── Page Layer
├── DOM Layer
├── Runtime State Layer
│     ├── dataLayer
│     ├── Cookies
│     ├── LocalStorage / SessionStorage
│     ├── JS variables
│     └── Application state
├── Consent Layer
├── Interaction Layer
├── Network Layer
└── Tagging Layer (Variables → Triggers → Tags)
```

The platform must be able to trace a chain like:

```
Click "Add to Cart" → DOM interaction → JS event → dataLayer.push()
→ ecommerce object → GTM trigger → GTM variables → GA4 / Meta / other tags
```

**Status:** the DOM/Page/URL layers and dataLayer *event* capture
(`observability/agent.js`'s `dataLayer.push` wrap) are implemented (Phase
0/0.5). Cookies, localStorage, and sessionStorage are **not yet captured
anywhere** — confirmed gap, see `docs/ROADMAP.md` Phase 1.6.

## 2. From URL inventory to Data Inventory

For every crawled page, the target output is not just "recommendations"
but a runtime state snapshot:

```
URL: /checkout/payment

dataLayer          Cookies              LocalStorage      DOM
├── event          ├── session_id       ├── cart_id       ├── product_id
├── ecommerce       ├── _ga              └── customer_id   ├── price
│   ├── value       └── marketing_consent                  └── currency
│   ├── currency
│   └── items[]     SessionStorage
└── user.user_id    └── checkout_step
```

Aggregated across a whole crawl, this becomes the **Website Data
Dictionary** (below).

## 3. Website Data Dictionary

Automatically identify variables (`customer_id`, `product_id`, `cart_id`,
`transaction_id`, `consent_status`, `campaign_id`, ...) and, per variable,
track: name, every source location it was observed at, data type, example
values, observation frequency, which pages have it / are missing it,
conditions it depends on (e.g. authenticated session), first/last
observed, confidence, and potential GTM usage.

```
Variable: customer_id
Sources: dataLayer.user.customer_id | localStorage.customerId | cookie.customer_id
Observed: 4,213 / 5,000 pages (authenticated: 4,190/4,200, anonymous: 23/800)
Potential use: GA4 User ID, CRM enrichment, personalization
```

## 4. Presence vs. availability — a required distinction

A variable existing somewhere in the app is not the same as GTM being
able to use it. The platform must distinguish, and label findings by,
exactly which of these is true:

- **Exists** — present in JS application state.
- **Exposed** — appears in `dataLayer` (or another GTM-readable surface).
- **Accessible** — GTM can read it through a valid variable mechanism.
- **Available at trigger time** — present at the moment the relevant
  trigger fires, not just eventually.
- **Consistently populated** — true across the expected journeys, not
  just once in testing.

Collapsing these into one "found: yes/no" bit is the single most common
way a tagging tool produces false confidence. Never do that.

## 5. dataLayer as a dynamic, evolving schema

Treat `dataLayer` as a structure that drifts over time and across pages,
not a static JSON shape. Build a schema model per event
(`event.ecommerce.items[]`, `event.user.user_id`, `event.page.page_type`,
...) and detect: new/removed/renamed keys, type changes, structural
changes, inconsistent values, missing values, duplicate events, and
sequencing/timing anomalies.

```
WARNING — event: purchase
transaction_id: 96% string, 4% number
currency: 82% INR, 15% USD, 3% missing
```

## 6. Cookies and browser storage as first-class data sources, not artifacts

Classify likely purpose (identity, auth, consent, attribution, campaign,
experiment, cart, preferences, session, personalization, analytics,
advertising) — but never assert purpose without evidence. Every
classification carries confidence and the evidence it's based on:

```
cookie: campaign_id
Likely purpose: Attribution (confidence: 87%)
Evidence: created after a campaign URL param | persists across pages
          | consumed by an analytics request | correlated with marketing scripts
```

## 7. Temporal behavior

The question is not just "does this variable exist" but "when does it
exist" relative to the page lifecycle (load → DOM ready → dataLayer init
→ hydration → interaction → dataLayer event → GTM trigger → tag
execution). A variable can be available at load but not before purchase,
or available 800ms after the trigger that needed it already fired — this
is a timing-class tagging failure distinct from a missing-data failure,
and must be reported as such.

## 8. Journey-level data maps

Beyond single pages, map data availability across a journey (Homepage →
Search → Product → Add to Cart → Cart → Checkout → Payment → Purchase),
stage by stage:

```
ADD TO CART
Required: product_id, product_name, price, currency, quantity
Found:    product_id ✓  product_name ✓  price ✓  currency ✓  quantity ✗
```

## 9. Missing-instrumentation detection, evidence-labeled

Always distinguish **Observed** / **Expected** / **Recommended** /
**Missing** / **Unknown**. Never state a business requirement ("you must
collect X") as if it were an observed fact — recommendations are
labeled as recommendations.

## 10. GTM as an intelligence layer, and a Tagging Dependency Graph

Model the relationship Website State → GTM Variables → Triggers → Tags
explicitly enough to answer "what would a Data Layer Variable read from
`ecommerce.value` feed downstream" (GA4 Purchase, Google Ads Conversion,
Floodlight, ...) and to build a literal dependency graph from a runtime
signal (a cookie, a dataLayer key) through to the tags/network requests
it ultimately drives. This graph is one of the platform's most valuable
assets long-term — it's what turns "we found a gap" into "here is exactly
what breaks and why."

## 11. Change detection over time

Maintain historical snapshots so a rename like `dataLayer.product.price`
→ `dataLayer.product.pricing.amount` is caught as a breaking change with
its downstream blast radius ("existing GTM variables/tags may no longer
receive price"), not silently absorbed. This is the product functioning
as a **Tagging Change Detection Platform**, conceptually similar to
infrastructure observability but pointed at a website's data/tagging
environment instead of servers.

## 12. Scale strategy

The architecture must not assume every URL gets manually or individually
inspected. Pipeline:

```
URL Discovery → Page Classification → Representative Page Selection
→ Runtime Execution → State Extraction → Normalization → Aggregation → Intelligence
```

E.g. 10,000 URLs → 18 page templates → 7 runtime patterns → 42 dataLayer
schemas → 12 cookie families → 9 journey types. Understand patterns, not
just collect raw volume. (`sitewide/templates.py`'s clustering is the
existing seed of this — see Phase 1.5 in `docs/ROADMAP.md`.)

**Explicit anti-goal:** do not become "a tool that dumps everything found
on a website." The pipeline is Observation → Normalization →
Classification → Correlation → Inference → Validation → Tagging
Intelligence — every stage after Observation exists to compress raw
findings into knowledge, not to enlarge the dump.

## 13. Evidence-first AI

AI sits *above* the evidence layer, never replacing it:

```
Raw Evidence → Structured Observations → Deterministic Rules → Correlations → AI Interpretation
```

Every AI conclusion must be traceable back to the observations that
produced it (matches the existing `Diagnosis.confidence` +
rule-attribution pattern in `diagnostics/rules.py` — this principle is
already load-bearing, just needs to extend to every new capability below).

---

## 14. Automated Browser Behavior & Runtime Event Intelligence

A second, additive major capability: the platform should not only
*discover* what exists on a page — it should *interact* with the page and
observe what happens as a consequence, automating the investigative
workflow a tagging engineer normally does by hand in Chrome DevTools /
GTM Preview / Network / Console / Application-Storage panels.

**Core principle:** don't just discover what exists. Interact, and
discover what happens.

**Status:** a real slice of this already exists and is shipped — not
starting from zero. `observability/session.py` + `observability/agent.js`
already drive a real browser (Playwright), execute scripted interactions
(`observability/scenario.py`), and capture DOM mutations, `dataLayer.push`
calls, console errors/`window.onerror`, `fetch`/XHR network calls, SPA
navigation (`pushState`/`popState`), and consent state — then
`correlation/journey.py` groups them into per-interaction
`TrackingJourney` records and `diagnostics/rules.py` runs 11 deterministic
rules to produce root-cause diagnoses. `sitewide/aggregation.py` already
does cross-page consistency checking and a per-template health matrix.
This is the foundation the items below extend, not a parallel system.

### What's genuinely new here (not yet built)

- **Before/after state diffing for cookies and storage.** Interactions
  are already observed for DOM/JS/dataLayer/network; cookies, localStorage,
  and sessionStorage snapshots (new keys, deleted keys, modified values)
  around each interaction are not captured at all yet. This is the same
  gap as §1/§6 above, applied to the interaction timeline instead of a
  page-load snapshot.
- **Broader interactive-element taxonomy for auto-discovery.** Today's
  candidate discovery (`recommend/heuristics.py`'s heuristics feeding
  `observability/scenario.py`'s `auto_scenario_from_recommendations`) is
  CTA/form-focused. Extending to hamburger menus, accordions, tabs,
  dropdowns, pagination, filters/sort, modals, video controls, download
  buttons, and elements that only render after scroll is a real gap.
- **Scroll investigation as a first-class interaction type**, at defined
  depths (25/50/75/90/100%), checking for corresponding
  scroll/visibility/dataLayer/network signals at each depth — distinct
  from the existing `IntersectionObserver` visibility watcher, which
  observes element-level impressions, not scroll-depth milestones.
- **Desktop-vs-mobile / cross-implementation consistency for the *same*
  business interaction.** `sitewide/aggregation.py` already checks "does
  `add_to_cart` fire consistently across pages in a template"; it does
  not yet check "does the *same conceptual action* (add to cart) fire a
  *differently-named or differently-shaped* event depending on which UI
  surface triggered it" (product page vs. quick-view vs. search result vs.
  recommendation widget). This is a distinct, valuable cross-cutting
  analysis, not a duplicate of template consistency.
- **Timing-delay findings as their own class.** "The JS error immediately
  preceding a missing event" rule exists; "a variable existed but arrived
  N milliseconds after the trigger that needed it already fired" is a
  different, currently-undetected failure mode worth its own rule.
- **A Runtime Event Map** — one matrix, interaction × {JS, dataLayer,
  Network, GTM}, across the whole site, as a single at-a-glance view.
  Conceptually adjacent to the existing site health matrix
  (`sitewide/report.py`) but keyed by interaction type rather than by
  page/template.
- **Interaction Trace as a first-class, drillable record** — evidence
  chain from Finding → Interaction → Element → Timestamp → JS event →
  dataLayer event → storage change → network request, so a finding is
  always reproducible, not just assertable. `TrackingJourney` already
  carries most of this; formalizing it as an explicitly-traceable object
  (rather than an internal correlation detail) is the gap.

### What this explicitly is not

Not a rewrite of Phase 0.5/1.5. Every item above is an extension point on
an existing, working subsystem (new observer types in `agent.js`, new
diagnostic rules in `diagnostics/rules.py`, a new aggregation view
alongside `sitewide/aggregation.py`), following the same pattern that
took Phase 1.5 from "diagnose one journey" to "diagnose a whole site."

---

## Product evolution stages

1. **Website Discovery** — URLs, DOM, pages. *(shipped, Phase 0)*
2. **Runtime Discovery** — dataLayer, cookies, storage, JS state, network.
   *(dataLayer/network/DOM partially shipped via Phase 0.5/1.5; cookies/
   storage not yet — Phase 1.6)*
3. **Data Intelligence** — variables, events, schemas, relationships,
   availability (Data Dictionary, presence-vs-availability, schema drift).
4. **Tagging Intelligence** — GTM variables/triggers/tags, dependency
   graph, missing instrumentation.
5. **Continuous Monitoring** — changes, regressions, schema drift, tagging
   failures. *(historical health scores + regression alerting shipped in
   Phase 1.5; full schema-drift detection is new.)*
6. **AI Tagging Copilot** — root-cause narratives like "GA4 purchase is
   firing, but 9% of events have `ecommerce.value = undefined`, which
   began after deployment X, likely because the checkout app's pricing
   object changed from `product.price` to `product.pricing.amount`" —
   answerable only once stages 1–5 exist as queryable, evidence-backed
   history, not before.

See `docs/ROADMAP.md` for how these stages map onto concrete, sequenced,
sized work.

---

## 15. Positioning relative to Playwright: discovery layer, not a replacement

Playwright verifies what an engineer already knows should happen. This
product's job is the step before that: discover what nobody knew needed a
test yet. Engineers currently have to manually investigate a site in
DevTools before they can even write a Playwright assertion — that manual
investigation is exactly what §14's browser investigation engine
automates.

**Two-stage quality workflow:**

```
Automated Browser Investigation → Runtime Behavior Discovery
→ Potential Issue / Anomaly → Evidence Captured → Test Candidate
→ PLAYWRIGHT → Formal Verification → PASS / FAIL
```

The product never self-certifies a finding as a confirmed defect. It
distinguishes: **Observed → Potential issue → Suspected defect → Requires
verification → Confirmed defect**. This is a refinement of, not a
replacement for, `Diagnosis.confidence`'s existing
Confirmed/Highly-likely/Possible/Needs-investigation scale
(`diagnostics/rules.py`) — that taxonomy is already the right shape; the
new "Test Candidate" concept below is what's actually net-new.

### Test Candidates — the net-new artifact

A **Test Candidate** is a structured, evidence-backed hypothesis an
engineer reviews and turns into a real Playwright test — not an assertion
the product makes on its own authority:

```
TEST CANDIDATE
Name: Add-to-cart should expose quantity
Observed: add_to_cart event exists
Observed problem: quantity is missing
Evidence: 23 product pages
Suggested verification:
  1. Open product page  2. Locate Add to Cart  3. Capture dataLayer
  4. Click Add to Cart  5. Locate add_to_cart event
  6. Assert quantity exists  7. Assert quantity has the expected type
```

The product may emit Playwright pseudocode or a draft implementation, but
the required output is test *intent* plus *evidence* — a draft script
without traceable evidence is not a shippable Test Candidate.

**Categories:** event existence (interaction → no event observed), event
payload (event exists, required field missing), data type (`price =
"2499"` where a number was expected), timing (variable available only
after the tag that needed it already fired), consistency (same business
action names its event differently — or doesn't fire one — depending on
which UI surface triggered it), network transmission (dataLayer + GTM
fire, no analytics request follows), storage behavior (interaction
implies a cart/state change that never shows up in storage), consent
behavior (a tracking request fires before consent was granted), and
**regression** (a field present in a previous crawl/version's event is
absent in the current one).

Regression-category candidates connect to existing infrastructure rather
than needing new comparison logic from scratch:
`version_control/{snapshot,diff}.py` already diffs structural
pages/elements/recommendations crawl-to-crawl, and
`sitewide/history.py` already tracks health-score regressions over time.
What's missing is the finer grain this vision calls for — a specific
event's specific field flipping from present to absent between two
crawls, not just an aggregate score drop.

### Cross-implementation comparison stays central

The same "does the same conceptual interaction behave identically
everywhere it appears" analysis from §14 is what makes consistency-class
Test Candidates possible — product page vs. quick-view vs. search result
vs. recommendation widget vs. mobile, checked as one comparison, not N
independent per-page findings.

### Full-pipeline positioning

```
URL Discovery → Page Classification → Automated Browser Agent
→ {DOM/JS, Runtime State, Network} → Event Correlation
→ Tagging Intelligence → Issue Discovery → Test Candidates
→ PLAYWRIGHT → Automated Verification → CI/CD Regression Protection
```

The crawler is the discovery mechanism; the browser agent is the
observation mechanism; the runtime/state engine is the data-understanding
mechanism; correlation is the intelligence mechanism; Playwright is the
verification mechanism the product hands off to, not one it competes
with.

---

## 16. Automated Script Impact & Web Performance Intelligence

A fourth major pillar, combining tagging intelligence with performance
intelligence: investigate every script running on a page (first-party,
GTM, analytics, ads, consent, personalization, A/B testing, chat,
heatmaps, social, payment, fraud, video, support widgets), measure the
page's performance, then run **controlled isolation experiments** —
disable one script, one group, or all non-essential scripts, and measure
the difference. This is the pillar with the **least existing overlap**:
confirmed by search, there is zero performance-measurement code anywhere
in the repo today (no Lighthouse, Web Vitals, CDP profiling, or
throttling). Everything in this section is net-new, unlike §14/§15 which
mostly extend the already-shipped Phase 0.5/1.5 observability layer.

**Positioning:** inspired by Lighthouse CI's measurements (LCP, INP, CLS,
FCP, TBT, Speed Index) but not a Lighthouse wrapper — the differentiator
is the isolation-experiment layer Lighthouse doesn't have. The product
should get to statements like *"This page has poor INP. We observed 14
scripts executing during the affected interaction. Disabling Script X
improved median INP by 92ms and cut main-thread execution by 140ms across
controlled runs. Script X is also responsible for these tagging
behaviors — this is a performance/tagging trade-off worth investigating,"*
not *"Lighthouse says this page is slow."*

### Pipeline

```
Website → Browser Investigation → Runtime + Script Discovery
→ Performance Measurement → Script Isolation Experiments
→ Causal Comparison → Performance Intelligence
```

### Core capabilities

- **Performance baseline per page** — LCP/INP/CLS/FCP/TBT/Speed Index,
  JS transferred/parsed/execution time, request count — aggregated over
  multiple runs (median/percentile, never a single-run number).
- **Script Inventory** — per script: URL, domain, first/third-party,
  initiator, load mechanism (async/defer), load timing, transfer/resource
  size, execution time, long tasks, network/DOM/storage activity
  generated, and inferred business purpose (analytics, ads, consent,
  personalization, A/B testing, chat, heatmap, social, payment, fraud,
  video, support, recommendation).
- **Script dependency graph** — e.g. GTM → {GA4, Meta Pixel, Floodlight,
  Hotjar}, or Consent Manager → GTM → Analytics → Advertising — because
  disabling one script can eliminate several downstream ones, and the
  isolation experiments below need to account for that rather than
  double-count savings.
- **Isolation experiments** — individual script, script group (analytics/
  ads/personalization/chat/social/consent/tag-management/heatmaps/A-B-
  testing), and an all-non-essential-scripts-off run, each compared
  against baseline. Report **observed experimental impact** — explicitly
  not "proven causality" beyond what a controlled A/B run of that exact
  script actually supports; correlation vs. inferred causality are always
  labeled, following the same evidence-first discipline as the rest of
  this vision (§13).
- **Tagging-vs-performance trade-off** — join a script's measured
  performance cost (LCP/TBT/requests/JS execution delta) with what it's
  already known to do from the tagging intelligence side (which events
  it's associated with, e.g. Meta Pixel → Purchase/AddToCart/ViewContent)
  — the same evidence-linking discipline as §14, applied to performance
  data instead of tagging data.
- **Script ranking** — order scripts by measured impact (TBT/JS
  execution/requests added), so the output is "script X costs 180ms TBT"
  rather than an undifferentiated "JavaScript is slow."
- **Web Vitals attribution with evidence** — for LCP/INP/CLS, show *what
  a script actually did* (delayed rendering, blocked the main thread,
  added a long task, injected content that shifted layout) rather than
  just assigning blame by correlation.
- **Performance regression detection** — ties into the *existing*
  change-detection infrastructure (`version_control/{snapshot,diff}.py`,
  `sitewide/history.py`) the same way §15's regression Test Candidates
  do: a newly-introduced script correlated with a TBT/LCP regression
  between two crawls, not a parallel history mechanism.
- **Page-type/template aggregation** — reuses `sitewide/templates.py`'s
  existing clustering (product/category/checkout/etc.) rather than a new
  classifier, to report performance and major contributors per template
  ("Checkout: median LCP 3.7s, major contributors: payment SDK, fraud
  detection, analytics, chat").
- **Controlled test environment** — standardized browser version,
  viewport, CPU/network throttling, region, cache state, device profile,
  consent state, login state, and run count, with the exact configuration
  stored alongside every result so comparisons stay meaningful over time.
- **Playwright integration** — performance findings can also produce Test
  Candidates (§15's mechanism, reused): e.g. "verify script does not load
  before consent" or "verify performance stays within threshold" as a
  suggested regression test, with the custom measurement engine providing
  the detailed numbers Playwright assertions alone can't.

### What this needs that doesn't exist yet

Everything: a CDP-level (Chrome DevTools Protocol, via Playwright)
performance-metrics collector, network-request interception to block
individual scripts/domains for the isolation experiments, a script
inventory/classification model, and a dependency-graph builder. This is
the largest, most architecturally distinct addition of the four pillars —
treat it as its own phase in `docs/ROADMAP.md`, not a small extension.

### Updated full architecture

```
                         WEBSITE
             ┌──────────────┼──────────────┐
        URL Discovery   Browser Agent   Script Discovery
             │              │              │
          DOM/Data     Runtime State    Dependencies
             └──────────────┼──────────────┘
                    EVENT CORRELATION
             ┌──────────────┼──────────────┐
       Tagging Intel   Issue Discovery   Performance Intel
             │              ↓              │
             │        Test Candidates ─────┘
             │              │
             │         Playwright
             └──────────────┼──────────────┘
                  Continuous Monitoring
```

---

## 17. GTM Client/Server Execution Intelligence & the Tag Execution Graph

A fifth pillar, formalizing and extending §10's "Tagging Dependency
Graph" and §16's script dependency graph into one central abstraction,
plus genuinely new capability: understanding GTM and website
instrumentation as a **distributed system**, not a script embedded in
HTML — client-side GTM, server-side GTM, duplicate/conflicting
implementations, and background scripts that only activate after load.

**Core requirement:** don't assume everything relevant to tagging is
discoverable from HTML or static JS alone. Investigate code + runtime +
browser events + DOM + dataLayer + network + script dependencies +
server-side tagging indicators *together*.

### The Tag Execution Graph

One abstraction, superseding §10's narrower "Tagging Dependency Graph,"
attempting to reconstruct the full observable chain:

```
Website Code → Script → JS Execution → Browser/DOM Event → dataLayer Event
→ GTM Container → GTM Trigger → GTM Tag → Network Request
→ Tagging/Collection Endpoint → Server-side GTM/Processing → Downstream Vendor
```

Not every stage is always observable. Every edge in the graph is labeled
with exactly how well-supported it is — **Observed / Inferred / Suspected
/ Unknown / Not observed** — never fabricated. This is the same
evidence-first discipline as everywhere else in this document (§13),
applied as an explicit per-edge label rather than a single confidence
score on the whole finding.

### What's genuinely new (beyond §10/§14/§16)

- **Static code intelligence**: inspect source/loaded JS for GTM
  container snippets (including multiple/duplicate container IDs,
  dynamically-injected GTM, GTM loaded after consent/interaction/DOM-
  ready) and hard-coded vendor implementations (GA4, Google Ads,
  Floodlight, Meta Pixel, Adobe Analytics/AEP, and other analytics/ads/
  experimentation/personalization/heatmap/chat/payment/video SDKs). The
  goal is identifying *which code can participate in tagging behavior*,
  not producing a bare script list — this feeds the Tag Execution Graph's
  nodes, and feeds §16's script inventory rather than duplicating it.
- **Duplicate/conflicting implementation detection**: two GTM containers,
  GTM + a hard-coded equivalent (e.g. GTM *and* a direct Meta Pixel),
  etc. Never auto-classified as a defect — investigated for whether they
  actually produce duplicate *runtime* behavior (two equivalent network
  requests observed for the same interaction), with evidence: triggering
  interaction, container/tag IDs, requests, destinations, timestamps,
  payload similarity, affected pages.
- **Server-side GTM awareness**: the browser may never expose a
  server-side container directly, so detect *indicators* instead — a
  first-party collection/proxy endpoint, one browser event fanning out to
  multiple vendor destinations, request-transformation patterns, known
  tagging-endpoint shapes, config exposed in JS. Always hedged
  ("Likely server-side tagging endpoint," "Server-side relationship not
  confirmed") — this is the one area of the whole vision most prone to
  false-positive claims, so the evidence-first discipline matters most
  here.
- **Background/post-load script intelligence**: continue observing after
  `DOMContentLoaded`/load — after consent, after scroll, after SPA
  navigation, after AJAX, after lazy-loading, after a checkout step, after
  a delayed/timer-based init. A script dormant at page load can become
  highly active later; the investigation window must not end at load.
- **Tag Execution Graph ↔ Performance Intelligence (§16) integration**:
  attribute a measured performance cost (long tasks, INP degradation) to
  a specific position in the execution chain (e.g. "GTM → Vendor Loader →
  Advertising SDK → 5 additional scripts → long task → INP degradation"),
  not just to an isolated script in §16's ranking.
- **Causality labels, more granular than §13's five-point scale, for
  this pillar specifically**: Observed / Correlated / Experimentally
  associated / Inferred / Confirmed — e.g. never "Script X caused the INP
  problem," always "disabling Script X produced a median 92ms improvement
  in INP under controlled test conditions."
- **A richer per-finding evidence schema**: finding ID, page, page type,
  URL, interaction, timestamp, script, GTM container/tag/trigger,
  dataLayer event, DOM event, network request, endpoint, initiator,
  server-side indicator, performance metrics, experiment results,
  confidence, severity — one record a user can walk from Finding →
  Interaction → Event → GTM → Script → Network Request → Performance
  Impact. This is §14's Interaction Trace and §16's evidence discipline,
  unified into one schema now that a finding can originate from either
  side.

### Positioning (unchanged, restated for this pillar)

*"Don't just tell me that a tag or script exists. Show me how it
participates in the browser execution chain, what it triggers, whether it
reaches server-side tagging, what downstream behavior it produces, and
what measurable cost it imposes."* Playwright remains the verification
layer (§15); this pillar, like the others, is discovery and evidence, not
a Playwright replacement.
