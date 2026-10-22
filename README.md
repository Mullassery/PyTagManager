# PyTagManager

[![Graphify](https://img.shields.io/badge/Graphify-knowledge%20graph-blue)](https://github.com/Graphify-Labs/graphify)

[![CI](https://github.com/Mullassery/PyTagManager/actions/workflows/ci.yml/badge.svg)](https://github.com/Mullassery/PyTagManager/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.5.0-blue)](https://github.com/Mullassery/PyTagManager/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-pytagmanager-blue)](https://pypi.org/project/pytagmanager/)

## Problem

Google Tag Manager makes it easy to create tags, triggers and variables — and
hard to explain why the resulting implementation does not match what the
website or the measurement plan expects. Engineers still hand-inspect pages,
step through GTM Preview one interaction at a time, guess which variable is
empty, and discover duplicate or unreachable tags only after an event fails to
arrive.

## What PyTagManager does

PyTagManager is a **debugging and implementation-intelligence tool for Google
Tag Manager**. It combines evidence from the live website and the GTM
configuration:

- **Website discovery with MudFish** — crawl/scrape an authorized domain,
  inspect static HTML and loaded JavaScript, rendered DOM, dataLayer, network
  requests, consent state, storage and interactions.
- **GTM container understanding** — import GTM container JSON or YAML, inspect
  tags, triggers, variables, `{{variable}}` references and firing conditions,
  and explain why a tag cannot behave as configured.
- **Runtime diagnosis** — reproduce a journey in a real browser and correlate
  DOM events → dataLayer → GTM → analytics requests with console errors and
  consent state.
- **Targeted remediation** — explain the specific tag/trigger/variable or page
  evidence at fault, produce a reviewable GTM import/diff where applicable, and
  verify the result at runtime. Source patching/PR generation is not implemented
  yet; proposed fixes always require explicit review.

**PyTagManager is not a replacement for Google Tag Manager, and it is not a
measurement/CDP/attribution platform.** GTM remains the tag manager. The Web,
iOS and Android SDKs plus the collection endpoint are secondary debugging tools
for testing first-party event flow and same-domain PyTagShield routing, not a
measurement product.

The existing crawler, exporters, Data Dictionary, diagnostics and control plane
remain available. Start with [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md);
the product vision is in [`docs/VISION.md`](docs/VISION.md).

## Common debugging workflows

```bash
# Inspect an exported GTM container (JSON or YAML) for likely faults.
pytagmanager gtm inspect gtm-container.yaml
pytagmanager gtm inspect gtm-container.yaml --format json -o findings.json

# Drive a real browser and correlate runtime evidence with GTM/GA4.
pytagmanager diagnose https://example.com --max-pages 20
pytagmanager diagnose https://example.com/checkout --scenario purchase.yml --format json

# Discover pages and page-code/tagging evidence across the domain.
pytagmanager crawl https://example.com --render --sniff-analytics --max-pages 50

# Export a managed revision as a reviewable GTM container snapshot.
pytagmanager gtm export GTM-ABC1234 --output gtm-review.yaml

# Import a GTM snapshot as a draft revision; nothing is activated.
pytagmanager gtm import gtm-container.yaml GTM-ABC1234 --json
```

## Use cases

- **Explain a tag that will never fire** — `gtm inspect` finds tags with no
  firing trigger, dangling trigger references, undefined variables and duplicate
  event delivery before anyone opens GTM Preview.
- **Explain a tag that fires incorrectly** — `diagnose` correlates the browser
  interaction, dataLayer push, GTM trigger, tag and network request, with
  confidence-labeled root causes.
- **Catch duplicate direct + GTM instrumentation** — static and runtime
  evidence show whether two implementations are producing duplicate events.
- **Review a GTM container before import** — inspect a JSON/YAML snapshot,
  apply the proposed correction, and keep the original for rollback.
- **Catch tracking regressions** — `diff` crawl snapshots or `diagnose
  --site-wide --history` for historical health changes.
- **Not yet a good fit for:** kiosk/IoT, visual/screenshot-only element
  grounding, or cloud-LLM-backed intent classification. Mobile SDK sources exist
  but their verification status is explicitly limited; see
  [Multi-platform SDKs and collection](#multi-platform-sdks-and-collection).

## Installation

```bash
pip install pytagmanager
```

> **PyPI is current at v0.5.0.** The published wheel is macOS arm64 plus an
> sdist; Linux/Windows installs build from source and need a Rust toolchain.
> See [What's not working](#whats-not-working--open-issues).

Installs the core CLI (`crawl`, `diff`) with no extra dependencies beyond
`click`. Both `dictionary` and `diagnose` drive a real browser (Playwright)
and need the `diagnostics` extra:

```bash
pip install 'pytagmanager[diagnostics]'
playwright install chromium   # one-time browser download
```

For local development instead (building the Rust extension from source):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install maturin pytest
maturin develop          # builds the Rust extension, installs pytagmanager editable

pytagmanager crawl https://example.com --max-pages 20 --export gtm -o out.json
```

`--export` accepts `gtm`, `ga4`, `segment`, `snowplow`, `tealium`,
`rudderstack`, or `adobe_tags` (see `python/pytagmanager/export/base.py`'s
`EXPORTERS` registry).

Managed revisions can also be projected into a startup configuration for
[PyTagShield](https://github.com/Mullassery/PyTagShield). The projection is
conservative: only server-representable event-name routing is exported, and
unsupported triggers, destinations, parameters, or credentials fail closed.

```bash
pytagmanager config pytagshield-export GTM-ABC1234 \
  --pseudonymize-salt "$PYTAGSHIELD_PSEUDONYMIZE_SALT" \
  --output pytagshield.yaml
```

The output is JSON (valid YAML for PyTagShield) and is written mode `0600`
because resolved credentials are embedded. See
[`docs/architecture/pytagshield-integration.md`](docs/architecture/pytagshield-integration.md).

## Multi-platform SDKs and collection

The web control plane can publish immutable public configuration and SDK assets
to a self-hosted CDN tree, and run a standalone collection endpoint:

```bash
# Publish the active environment to a filesystem CDN tree.
pytagmanager cdn publish GTM-ABC1234 Production --root ./cdn --json

# Verify hashes, config integrity and latest pointers.
pytagmanager cdn verify --root ./cdn

# Run collection without forwarding (development / debugging).
pytagmanager serve-ingest --container GTM-ABC1234 --port 8080

# Persist event-id claims across restarts and same-host worker processes.
pytagmanager serve-ingest --container GTM-ABC1234 \
  --dedupe-db /var/lib/pytagmanager/dedupe.sqlite3

# Forward accepted, validated events to a real PyTagShield instance.
pytagmanager serve-ingest \
  --container GTM-ABC1234 \
  --path /collect \
  --pytagshield-url https://shield.example.com \
  --pytagshield-token-ref env:PYTAGSHIELD_INGEST_TOKEN
```

For a persistent systemd + reverse-proxy deployment, see
[`deploy/collection/README.md`](deploy/collection/README.md). Browser and
server-side events should share one public `/collect` origin; collector-level
`event_id` dedupe does not apply to traffic sent directly to PyTagShield.

The collection endpoint exposes `GET /healthz` (configuration and limits, no
secrets) and `POST /api/v1/events`. `GET /healthz` plus the SDK diagnostics
snapshot (`PyTagManager.snapshot()` in Swift/Kotlin, `debugSnapshot()` in the
Web SDK) are intended for safe debugging: they report config version/source,
queue depth, last sanitized diagnostics and forwarding status without echoing
event properties or secrets.

| SDK | State |
| --- | --- |
| Web | Implemented in `sdk/web/`; build and 11 Node tests pass |
| iOS | Swift package in `sdk/ios/`; library builds, 19 executable checks pass, UIKit lifecycle observer added; XCTest needs Xcode/CI |
| Android | Kotlin library in `sdk/android/`; `./gradlew :sdk:build` passes with lint and 28 JUnit tests (debug + release); no emulator/device tests |

Public configuration never contains destination credentials or tag parameters.
The collection endpoint validates and deduplicates events (in memory by default,
or durably with `--dedupe-db`) but does **not** perform destination routing;
PyTagShield (or another adapter) owns that policy.
See [`docs/architecture/multiplatform-extension.md`](docs/architecture/multiplatform-extension.md)
for contracts, cache layout, security boundaries, exact test commands and
limitations.

## Architecture

- **Rust core** (`src/`, via [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs)): async crawler (link discovery, sitemap.xml, robots.txt, BFS with dedup) and a semantic DOM graph engine (XPath/CSS/stable-selector generation per element).
- **Python layer** (`python/pytagmanager/`): orchestration, rule-based tracking recommendations, exporters, crawl-snapshot diffing, a Website Data Dictionary, an optional local-LLM intent classifier, and Tracking Observability & Diagnostics (`observability/`, `correlation/`, `diagnostics/`, `analytics_api/`, `reporting/`, `sitewide/`), built on top of the compiled Rust extension.

```
pytagmanager crawl <url>
        │
        ▼
  Rust: crawl + parse each page into a SemanticGraph
        │
        ▼
  Python: recommend_for_graph() — rule-based CTA/form detection
        │
        ├──▶ export/{gtm,ga4,segment,snowplow,tealium,rudderstack,adobe_tags}.py
        │
        └──▶ version_control/snapshot.py — save a snapshot for `pytagmanager diff`
```

### Client-Rendered Crawling (`pytagmanager crawl --render`, needs `[diagnostics]`)

A static crawl only ever sees a page's raw HTTP response body. Most modern
sites inject their real content (and their CTAs) via JS after load, so a
static crawl of one produces zero recommendations — not because there's
nothing there, but because the crawler never saw it. `--render` re-fetches
each discovered page through a real headless browser instead, so the
DOM graph (and everything downstream of it) is built from what a visitor
actually sees:

```
pytagmanager crawl <url> --render [--screenshots-dir DIR] [--sniff-analytics] [--simulate-interactions]
```

- **Rendered DOM graph**: `runtime/renderer.py` loads the page in Chromium,
  waits for it to settle, and feeds the *live* `page.content()` HTML back
  through the same `_core.parse_html()` the static crawl uses — no Rust
  changes needed, no separate recommendation logic.
- **`--screenshots-dir DIR`**: saves 4 real PNGs per page (desktop/mobile ×
  above-fold/full-page).
- **`--sniff-analytics`**: reports which analytics vendors are already
  observed firing network requests, and whether `window.dataLayer` is
  present — reusing the same vendor-signature list `scan-tags` and
  `pytagmanager perf` already match against, not a second list.
- **`--simulate-interactions [--interaction-top-n N]`**: clicks the page's
  top-N highest-confidence recommended elements (fresh browser context per
  candidate) and reports real DOM mutations and network requests observed
  — a selector that can't be interacted with is reported with an error,
  not fatal to the rest of the crawl.

**Disclosed trade-off**: every page is fetched twice under `--render` (once
by the Rust crawler for URL discovery, once by the browser for the actual
render) — discovery-without-fetching-bodies would need Rust-side changes
out of scope for this pass.

### Website Data Dictionary (`pytagmanager dictionary`, needs `[diagnostics]`)

```bash
pip install 'pytagmanager[diagnostics]'
pytagmanager dictionary https://example.com --max-pages 20 --format json -o dictionary.json

# Label each variable's Exists/Exposed/Accessible presence-vs-availability status:
pytagmanager dictionary https://example.com --presence-labels

# Classify cookie/localStorage/sessionStorage purpose (fixed taxonomy, evidence + confidence):
pytagmanager dictionary https://example.com --purpose-classifier heuristic   # or: ollama

# Diff against a previous run for per-field dataLayer schema drift:
pytagmanager dictionary https://example.com --compare-to dictionary.json
pytagmanager dictionary https://example.com --gtm-config gtm-container.json
pytagmanager diagnose https://example.com --site-wide --history health.json --fail-on-regression
```

Drives a real browser session (same as `diagnose`) to build a variable-level
inventory across dataLayer, cookies, and storage: source path, inferred type,
example values, observed frequency, which pages have/lack it
(`python/pytagmanager/dictionary/`). This is Phase 1.7 of `docs/ROADMAP.md`,
shipped except for one enrichment: "potential GTM usage" / a GTM blast-radius
narrative on drift findings needs live GTM container config to cross-reference
against, which needs real credentials this environment doesn't have — see
[What's not working](#whats-not-working--open-issues).

- **`--presence-labels`**: Exists/Exposed/Accessible, derived from each
  variable's source (dataLayer fields are Accessible via GTM's built-in Data
  Layer Variable; cookies via the built-in 1st Party Cookie variable;
  localStorage/sessionStorage are only "possibly accessible," since no
  built-in GTM variable type reads them).
- **`--purpose-classifier`**: classifies cookies/storage against a fixed
  taxonomy (identity/auth/consent/attribution/campaign/experiment/cart/
  preferences/session/personalization/analytics/advertising) from
  deterministic evidence (key-name pattern, cross-page persistence,
  co-occurrence with a campaign URL param) — `heuristic` uses that evidence
  directly, `ollama` re-ranks it via a local Ollama model with automatic
  fallback if Ollama isn't reachable.
- **`--compare-to`**: diffs two dictionary JSON exports for added/removed
  fields, type-distribution shifts (e.g. `transaction_id: 96% string, 4%
  number`), and possible renames (a hedged heuristic on leaf-name similarity
  + type match within the same dataLayer event, never asserted as fact).

### Tracking crawl-to-crawl changes

```bash
pytagmanager crawl https://example.com --save-snapshot baseline.json
# ... site changes, or crawl again later ...
pytagmanager crawl https://example.com --save-snapshot latest.json
pytagmanager diff baseline.json latest.json
```

Reports added/removed pages, added/removed/changed DOM elements (matched by
stable selector where available), and added/removed tracking
recommendations. See `python/pytagmanager/version_control/`.

### AI business intent classification (optional, local-only)

`pytagmanager.intent.ollama_classifier.OllamaIntentClassifier` implements
the same `IntentClassifier` interface as the deterministic heuristics
engine, but backed by a locally running [Ollama](https://ollama.com) model
(default `qwen2.5:0.5b`) instead of keyword matching. It's wired into
`crawl` directly:

```bash
pytagmanager crawl https://example.com --intent ollama
pytagmanager crawl https://example.com --intent ollama --ollama-model llama3 --ollama-url http://localhost:11434
```

or from Python, both via `recommend_for_graph(graph, classifier=...)` and
directly against the classifier:

```python
from pytagmanager import OllamaIntentClassifier, PageContext, recommend_for_graph

classifier = OllamaIntentClassifier()  # talks to http://localhost:11434
recs = recommend_for_graph(graph, classifier=classifier)

# or classify a single node directly:
result = classifier.classify(node, PageContext(url=page_url, page_title=title))
```

(Don't confuse this with `OllamaPageTypeClassifier`, a different classifier
used for `diagnose --site-wide --semantic-labels` template labeling below.)
If Ollama isn't reachable, `classify()` falls back automatically to the
deterministic keyword heuristic rather than raising — this runs entirely
locally, with no cloud LLM API calls or credentials required; see
`docs/ARCHITECTURE.md` for where a future cloud-LLM-backed classifier would
plug in via the same `IntentClassifier` interface.

## Tracking Observability & Diagnostics (optional, `pytagmanager diagnose`)

PyTagManager is not a replacement for Google Tag Assistant or GTM's own
Preview mode — those tools tell you a tag fired. Tracking Observability
answers a different question: **what happened, what should have happened,
where did they diverge, and why?** It drives a real browser, correlates
the full chain, and produces a plain-language diagnosis instead of a raw
event log:

```
Browser interaction → DOM mutation → dataLayer → GTM → GA4 → network request
```

```bash
pip install 'pytagmanager[diagnostics]'
playwright install chromium   # one-time browser download

# Crawl the site, auto-derive test interactions from recommend_for_graph()
# (the same static analysis `pytagmanager crawl` uses), verify each one at
# runtime, and print a human-readable health report:
pytagmanager diagnose https://example.com --max-pages 20

# Or test one explicit hand-authored journey instead of crawling:
pytagmanager diagnose https://example.com/product --scenario add_to_cart.yml --format json
```

A scenario file (`--scenario`) is a named sequence of actions plus the
tracking behavior expected to result:

```yaml
journey:
  name: Add To Cart
  steps:
    - action: click
      selector: "[data-testid='add-to-cart']"
    - expect:
        datalayer_event: "add_to_cart"
```

### What it observes and correlates

- **Browser agent** (`observability/agent.js`, injected before any page
  script runs): click/submit/change, a targeted+debounced `MutationObserver`
  for dynamically-rendered elements, a `dataLayer.push` wrap (observes
  without ever replacing the original behavior — the site's real dataLayer
  keeps working exactly as before), `history.pushState`/`replaceState`/
  `popstate` for SPA navigation, `window.onerror`/`unhandledrejection`/
  `console.error`, `gtag('consent', ...)` state, `fetch()`/`XMLHttpRequest`
  interception for app-level API calls (excluding analytics endpoints,
  which the network layer below already covers), and an opt-in
  `IntersectionObserver`-based visibility watcher for impression tracking.
- **Runtime state snapshots** (`observability/state.py`): cookies,
  localStorage, sessionStorage, and the full `dataLayer` contents captured at
  a point in time, not just observed as events. Privacy-conscious by default —
  only key name/type/length captured unless `--capture-storage-values` is
  passed, and sensitive-looking keys stay redacted even then.
- **Correlation** (`correlation/journey.py`): groups the flat event stream
  into one `TrackingJourney` per user interaction using a time window plus
  selector/name matching — not "everything in the same 5 seconds is
  related."
- **Live config cross-check** (`analytics_api/`, optional):
  `GtmApiClient` pulls the GTM Management API's *live* (published)
  triggers/tags; `Ga4ApiClient` pulls GA4 Admin API config (custom
  dimensions/conversion events) and uses the GA4 Data API's realtime
  report to confirm an event was actually *ingested*, not just that a
  request was sent (a request can be dropped by an ad-blocker or rejected
  as malformed). Needs your own service-account credentials:
  `--gtm-container GTM-XXXXXXX --gtm-credentials sa.json --ga4-property 123456789 --ga4-credentials sa.json`.
- **Diagnostics** (`diagnostics/rules.py`): deterministic rules, no LLM —
  missing dataLayer event, event-name mismatch, GTM tag not executed,
  missing/unconfirmed GA4 request, duplicate events, consent blocking, a
  JS error immediately preceding a missing event, SPA navigation without a
  page-view, an app API call completing with no tracking event following,
  parameter loss between dataLayer and the analytics request, missing
  required ecommerce parameters (`transaction_id`/`currency`/`items`/
  `value`), and content-pattern PII detection in tracking payloads. Every
  `Diagnosis` carries both a `severity` (how bad) and a `confidence` —
  Confirmed / Highly likely / Possible / Needs investigation (how sure the
  rule is *why*, so a JS-error correlation is never presented with the
  same certainty as a directly-observed missing event).

### Site-Wide Tagging QA (`--site-wide`)

`pytagmanager diagnose <url> --site-wide` crawls the site, clusters pages
into templates (URL pattern + DOM structural similarity by default), and
reports cross-page consistency instead of one health report per journey:

```bash
pytagmanager diagnose https://example.com --site-wide --max-pages 100
pytagmanager diagnose https://example.com --site-wide --format json -o site_health.json

# Relabel templates using a local Ollama model's page-type classification
# instead of the URL-segment heuristic (falls back to the heuristic
# automatically if Ollama isn't running):
pytagmanager diagnose https://example.com --site-wide --semantic-labels
```

This surfaces findings a single-page report can't, e.g. "51 of 342
product pages don't generate `add_to_cart`" (a likely shared-component
regression, not 51 unrelated bugs) — see
`pytagmanager.sitewide.aggregation.analyze_template_consistency`. It also
flags statistical outliers *within* an otherwise-healthy template
(`sitewide/anomalies.py`), and — as of this release —
**cross-implementation consistency for the same business action**
(`sitewide/interaction_consistency.py`): does "Add to Cart" fire the same
event shape from the product page, quick-view, search results, and a
recommendation widget, regardless of which page template implements it?
Not compatible with `--scenario` (site-wide aggregation needs a crawl of more
than one page). Cross-journey checks like duplicate-purchase detection
run in both modes and appear as "Additional Findings". `--site-wide` also
includes a **Runtime Event Map**: one matrix, interaction ×
JS/dataLayer/Network/GTM coverage, site-wide (alongside, not replacing, the
per-template health matrix) — see `sitewide/event_map.py`.

#### Scroll-depth interactions and drillable traces

```bash
# Treat 25/50/75/90/100% scroll milestones as first-class interactions,
# each becoming its own journey checked against the same rule engine:
pytagmanager diagnose https://example.com --track-scroll-depth

# Add a formalized, drillable Interaction Trace per journey: Finding ->
# Interaction -> Element -> Timestamp -> JS/dataLayer/GTM/network events
# -> storage change:
pytagmanager diagnose https://example.com --trace --format json
```

`--track-scroll-depth` is off by default (most pages don't need
scroll-milestone journeys cluttering the report); when on, a diagnostic
rule (`rule_timing_delay`) also flags runtime state that changed
suspiciously long (>200ms, "Possible" confidence) after the trigger that
needed it already fired, using the same journey↔`StateDiff` join key
`--trace`'s storage-change step relies on.

#### Tracking health history + regression alerts

`--history` turns repeated `--site-wide` runs into a trend: it appends
this run's score to a JSON file and flags a regression against the
*previous* recorded run.

```bash
pytagmanager diagnose https://example.com --site-wide --history health_history.json

# Also alert a Slack incoming webhook (or any endpoint that accepts
# {"text": "..."}) when a regression fires:
pytagmanager diagnose https://example.com --site-wide \
  --history health_history.json \
  --alert-webhook https://hooks.slack.com/services/XXX/YYY/ZZZ \
  --alert-threshold 5
```

PyTagManager doesn't schedule itself — `--history`/`--alert-webhook` just
record and compare one run at a time. Run this on whatever cadence you
want via your own cron/CI; a regression alert only has a chance to fire
the next time you invoke it.

### Tag Execution Static Scan (`pytagmanager scan-tags`, needs `[diagnostics]`)

```bash
pytagmanager scan-tags https://example.com
pytagmanager scan-tags https://example.com --wait 5 --format json -o scan.json
```

Detects GTM container snippets and hard-coded vendor tracking
implementations (GA4, Google Ads, Floodlight, Meta Pixel, Adobe
Analytics/AEP/Launch, Segment, Mixpanel, Hotjar, Optimizely, Intercom,
Stripe, and others — 24 signatures total, curated not exhaustive) on a
page, including ones that only load after a delay: it snapshots the
rendered DOM at load and again after `--wait` seconds, and flags any
container/vendor present only in the second snapshot. This is Phase 1.85
item 1 of `docs/ROADMAP.md` (of 6) — the Tag Execution Graph that will
consume this alongside server-side-tagging detection isn't built yet, but
the static scan itself is real and standalone-reachable today, not
stranded behind the larger phase. See
`python/pytagmanager/tagexec/static_scan.py`'s module docstring for why it
scans real DOM elements (`<script src>`/`<iframe src>` attributes, inline
script bodies) rather than regexing the raw HTML text — the latter
false-positives on IDs that merely appear as string literals inside
unrelated, not-yet-fired event-handler code.

#### Duplicate/conflicting tag detection (`diagnose --detect-duplicate-tags`)

```bash
pytagmanager diagnose https://example.com --detect-duplicate-tags --format json
```

Flags duplicate/conflicting implementations (multiple GTM containers, GTM
alongside a hard-coded analytics vendor, the same vendor wired in twice)
— but, deliberately, a static shape alone is never reported as a finding
(a site can legitimately run two GTM containers for two unrelated
business units without ever double-firing anything). A candidate only
escalates to a `DuplicateFinding` once a real business interaction's
network requests corroborate duplicate firing: two or more analytics
requests for the same interaction, with a payload-parameter similarity
score. Phase 1.85 item 2 of 6.

#### Server-side tagging indicators (`diagnose --detect-server-side-tagging`)

```bash
pytagmanager diagnose https://example.com --detect-server-side-tagging --format json
```

Flags two hedged server-side GTM/tagging signals: a first-party network
request shaped like a GA4 Measurement Protocol hit (`tid`/`v`/`en` query
params, but served from the site's own domain — consistent with a
server-side GTM proxy), and one interaction's network requests spanning
more than one distinct external vendor host (consistent with — not proof
of — server-side fan-out to multiple destinations). **Every indicator is
hedged by construction**: confidence is always "Likely" or "Possible",
never "Confirmed" — server-side relaying isn't something a browser can
actually observe, only infer from request shape. Phase 1.85 item 3 of 6.

#### Tag Execution Graph (`diagnose --tag-graph`)

```bash
pytagmanager diagnose https://example.com --tag-graph --format json
```

Assembles everything above into one graph: static-scan nodes (GTM
containers, vendor scripts), Interaction Trace steps chained in temporal
order, duplicate-implementation findings, and server-side indicators —
every edge labeled with one of five evidence levels (`Observed` for
directly-captured transitions and runtime-corroborated duplicates,
`Inferred`/`Suspected` for server-side indicators matching that
indicator's own confidence, `Unknown`/`Not observed` reserved for
detectors not built yet). No edge is ever labeled with a stronger claim
than its source data supports. JSON output only — a full graph isn't
meant to be read as flat text; the text-format report just prints a
node/edge count. Phase 1.85 is now fully shipped (6 of 6 items) — item 4's
real, scoped gap (an SPA route change never reset the mutation/
visibility/scroll-depth observers' dedup caches, so a rebuilt element
reusing the same selector would silently stop being reported after the
first route) is fixed in `agent.js`.

### Test Candidates (`diagnose --test-candidates`, `dictionary --compare-to --test-candidates`)

```bash
# Diagnosis- and consistency-category candidates from a diagnose run:
pytagmanager diagnose https://example.com --site-wide --test-candidates --format json

# Regression-category candidates: a dataLayer field present in a previous
# crawl but missing from the current one:
pytagmanager dictionary https://example.com --compare-to baseline.json --test-candidates --format json
```

Turns findings from `diagnose`/`--site-wide`/the Data Dictionary into
structured, evidence-backed **Test Candidates** — not an assertion the
product makes on its own authority, but a hypothesis an engineer reviews
before formalizing as a real Playwright test (docs/VISION.md §15). Each
candidate carries a category (event existence/payload, timing,
consistency, network transmission, consent behavior, regression — two of
the nine VISION categories, data type and storage behavior, have no
generator yet since no existing rule detects either), a severity from a
five-stage scale that's **structurally capped at "Requires verification"**
— no generator ever self-certifies a "Confirmed defect", only a human or
a real Playwright run does — and a draft Playwright script
(`playwright_draft` in JSON output) that always ends in
`raise NotImplementedError`, so it can never be mistaken for a passing
test if run unreviewed. The same underlying problem observed across many
pages becomes one candidate with an evidence list, not one candidate per
page.

### Automated Script Impact & Web Performance Intelligence (`pytagmanager perf`, needs `[diagnostics]`)

```bash
# Baseline: real LCP/CLS/FCP/TBT/INP, aggregated over 3 runs (median), plus a script inventory.
pytagmanager perf https://example.com

# Isolation experiment: block one script and measure the difference.
pytagmanager perf https://example.com --isolate https://cdn.example.com/heavy-vendor.js

# Block a whole group (ads/analytics/heatmap/experimentation/chat/payment/video/tag_management),
# or every classifiable script at once:
pytagmanager perf https://example.com --isolate-group ads
pytagmanager perf https://example.com --all-off

# Real CDP CPU throttling, regression tracking, and Test Candidates:
pytagmanager perf https://example.com --isolate-group analytics \
  --cpu-throttling 4 --history perf_history.json --test-candidates --format json
```

The pillar VISION.md §16 describes as having "the least existing overlap"
with anything already built — genuinely new, not an extension of Phase
0.5/1.5's observability layer. **The isolation-experiment layer is the
actual differentiator** (inspired by Lighthouse's metrics, but Lighthouse
has no equivalent): block a script — plus everything downstream of it, so
blocking GTM correctly accounts for the GA4/Meta Pixel/etc. it loads too —
and re-measure against a baseline. Every result reports *observed
experimental impact* for that controlled run, never a general claim about
a script's cost on every page or visitor.

- Every metric is a real browser-native measurement (the standard
  `PerformanceObserver`/Performance Timeline API — not a Lighthouse
  wrapper or CDP tracing), never a single-run number.
- Script classification reuses Phase 1.85's vendor signatures
  (`tagexec.static_scan`), so a script's measured cost joins directly with
  what it's already known to do from the tagging side.
- `--cpu-throttling` is real (CDP `Emulation.setCPUThrottlingRate`), not a
  label; the exact environment (browser, viewport, run count, throttling)
  is persisted alongside every result so comparisons stay meaningful over
  time.
- **Disclosed, not fabricated**: per-script CPU execution time and
  long-task attribution aren't measured (would need CDP's JS Profiler
  domain); network-condition throttling (a "Slow 4G" preset) isn't wired
  in; "verify script does not load before consent" Test Candidates aren't
  generated (would need consent-state/script-timing correlation not built
  yet).

### Privacy

Telemetry never leaves your machine unless you supply GTM/GA4 credentials
yourself. `events.redact_payload` strips values under obviously-sensitive
keys (password, token, secret, credit card, SSN, ...) before a
`TrackingEvent` is even constructed, and `diagnostics.rules.rule_pii_leak`
separately scans payload *content* (not just key names) for
email/phone/SSN/credit-card patterns that leaked through an innocuous
field name. Runtime state capture applies the same discipline — see above.

### Limitations

- Network observation parses event names/params from GA4 hit query
  strings (`en=`, `ep.*`); batched Measurement Protocol POST bodies aren't
  parsed.
- A `Scenario`'s expectations are associated with its last action step's
  selector; multi-step funnels with per-step expectations aren't
  distinguished yet.
- `--site-wide` template detection defaults to a URL-pattern/DOM-fingerprint
  heuristic (a "Product" label is a naming coincidence from the URL, not
  semantic understanding) -- pass `--semantic-labels` for LLM-backed
  page-type classification instead, which still falls back to a
  deterministic URL-keyword heuristic if Ollama isn't reachable.

## Development

```bash
cargo test               # Rust unit tests (selectors, robots.txt, sitemap parsing, DOM parsing)
pytest tests/python -v   # Python tests (heuristics, exporters, diffing, intent classification, observability)
```

Tracking Observability's tests drive a real headless browser: run
`pip install 'pytagmanager[diagnostics]' && playwright install chromium`
once before `pytest` if you haven't already — CI does this too as of this
pass (see [What's not working](#whats-not-working--open-issues)).

macOS note: this repo includes `.cargo/config.toml` with the linker flags
PyO3 extension-module crates need for plain `cargo build`/`cargo test` to
work outside of maturin (maturin sets these automatically; raw `cargo`
doesn't).

## Related projects

Part of the Mullassery open-source family — PyTagManager sits at the *tagging/implementation* end of the customer-data stack:

- [ClusterAudienceKit](https://github.com/Mullassery/ClusterAudienceKit) — customer segmentation and audience intelligence
- [PyReverseETL](https://github.com/Mullassery/PyReverseETL) — quality-validated reverse ETL / data activation
- [MessageBirds](https://github.com/Mullassery/MessageBirds) — event-driven customer data and engagement platform
- [StatGuardian](https://github.com/Mullassery/StatGuardian) — runtime data-quality validation
- [PyTagShield](https://github.com/Mullassery/PyTagShield) — consent-aware, privacy-minimizing server-side event pipeline; PyTagManager can project managed revisions into its startup config
- [PyDeepMesh](https://github.com/Mullassery/PyDeepMesh) — dependency-graph and vulnerability intelligence
- [Browse all projects →](https://github.com/Mullassery?tab=repositories)

## Known issues and deferred work

**Blocked / failed:**
- GTM write/apply needs a resource mapper and live credentials; `gtm-plan` is the safe review path.
- Full Playwright CI rerun is pending after the Click fix.

**Rejected / deferred:**
- Visual/screenshot grounding, XDM modeling, and mobile platforms — not required for web QA.

Full shipped/blocked/rejected detail: [`QUEUE_STATUS.md`](QUEUE_STATUS.md).

## Contributing, security, and license

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the dev workflow and this
project's documentation-honesty policy, [`SECURITY.md`](SECURITY.md) for
vulnerability reporting and disclosed risk areas (this is a solo-maintained
project with no SLA), and [`CHANGELOG.md`](CHANGELOG.md) for release
history. Licensed under [Apache-2.0](LICENSE).

## What's working now (verified)

23 Rust tests + 683 Python tests, covering the CLI end-to-end (`crawl`,
`diff`, `dictionary`, `diagnose`, `gtm inspect/export/import`, repeated-run
`lighthouse-ci`, `cmp audit`), all 7 exporters, crawl-diffing, the shared event contract,
public-config/CDN publication, the collection endpoint with in-memory or
durable SQLite deduplication, plus — with real headless Chromium, not mocks —
the full Tracking Observability correlation and diagnostic-rules pipeline. The
Web SDK passes 11 Node tests; the iOS library builds with 19 executable checks
(XCTest pending); Android builds with lint and 28 JUnit tests (no device tests).
A fresh wheel install was smoke-tested end to end, including CDN SDK
publication.
See
[`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for the full built-and-reachable /
built-but-not-reachable / not-built / CI-status breakdown, including exactly
which roadmap phases are shipped vs. still pending.

## What's not working / open issues

- **Platform coverage:** the PyPI wheel is macOS arm64 only; Linux/Windows use
  the sdist and require Rust. A manylinux wheel build needs a proper CI
  toolchain (the local cross-compile attempt lacked `zig`).
- **CI was broken on every push since Tracking Observability & Diagnostics
  landed, until this pass**: `ci.yml` never installed the
  `pytagmanager[diagnostics]` extra or a Chromium binary, so pytest's
  collection phase failed outright with `ModuleNotFoundError: No module
  named 'yaml'` before running a single test. Fixed by adding the extras +
  `playwright install --with-deps chromium` steps to CI. Base `pip install
  pytagmanager` users were never affected — the CLI's `dictionary`/`diagnose`
  commands import these lazily inside their own function bodies, not at
  module load.
- **Live GTM API writes are not implemented.** GTM usage and drift
  blast-radius are shipped (`dictionary --gtm-config`, `gtm-plan`), and
  `gtm import` creates a reviewable draft revision from JSON/YAML, but
  publishing/activating a live GTM workspace still requires manual review and
  import. PyTagManager never auto-activates.
- **`ClaudeIntentClassifier`** referenced in `docs/ROADMAP.md`'s Phase 2 is
  planned, not implemented; the only real `IntentClassifier` implementations
  today are `OllamaIntentClassifier` and the deterministic heuristics.
- No open GitHub issues and no `TODO`/`FIXME` markers in `src/` or
  `python/` as of this pass — the gaps that exist are the deliberately
  deferred phases tracked in `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`
  (visual/screenshot grounding, XDM modeling, non-GTM platform importers, and
  kiosk/desktop/IoT platforms), not undocumented rot. Web/iOS/Android SDKs and
  the CDN/collection extension exist but have the explicit verification limits
  listed above.

## Project layout

```
Cargo.toml / pyproject.toml   # Rust crate + maturin/Python packaging
src/                          # Rust: crawler/ + dom/ (semantic graph, selectors)
python/pytagmanager/          # Python: discovery/ recommend/ intent/ export/ version_control/ cli.py
                               #         observability/ correlation/ diagnostics/ analytics_api/ reporting/
                               #         sitewide/ dictionary/ tagexec/ testintel/ perf/ runtime/
tests/python/                 # Python tests + HTML fixtures (Rust tests live next to their modules)
docs/VISION.md                 # north-star: what PyTagManager is for, independent of what's shipped
docs/ARCHITECTURE.md          # implemented vs. deliberately deferred, plus the full long-term spec
docs/ROADMAP.md               # phase-by-phase sequencing of the work
ROADMAP_HONEST.md             # short current-status companion to the above
```

## Lighthouse audits

Join real performance/accessibility evidence with tag diagnostics:

```bash
npm install -g lighthouse   # Apache-2.0 CLI; no Python package
pytagmanager lighthouse https://example.com --json
```

```python
from pytagmanager.audit.lighthouse import LighthouseRunner

report = LighthouseRunner().run("https://example.com")
print(report.categories, report.metrics)
```

The adapter normalizes category scores, LCP/TBT/CLS/INP/FCP/Speed Index, and
failing opportunities. A missing Lighthouse/Chrome binary raises
`LighthouseUnavailable`; scores are never fabricated.

### Repeated runs with honest CI assessment

One Lighthouse run is an anecdote. `lighthouse-ci` executes independent runs,
reports medians and observed ranges, retains failures instead of dropping them,
and makes a pass/fail judgement only against explicit budgets:

```bash
pytagmanager lighthouse-ci https://example.com \
  --runs 5 --min-runs 3 \
  --budget lcp_ms=2500 \
  --budget tbt_ms=200 \
  --budget cls=0.1 \
  --budget performance=0.9 \
  --fail-on-budget \
  --format json -o lighthouse-ci.json
```

Exit codes: `0` assessment completed and budgets (if any) passed, `1` a budget
failed or its metric was unavailable, `2` too few runs completed or too many
runs failed (unless `--allow-partial`). The JSON report includes every sample,
per-metric distributions, budgets, confidence, assessment and limitations.
It does not claim field (CrUX/RUM) performance, a universal speed verdict, or
downstream tag delivery. Use `--help` for the supported budget keys.

## CMP audit

`cmp audit` collects consent-platform evidence from one page: detected CMP
signatures, readable consent state, pre/post-choice analytics and advertising
requests, and reload persistence. It is read-only by default and never submits
a consent choice unless `--consent-action` is paired with
`--authorize-consent-interaction`; only use that in an isolated test environment
you control.

```bash
pytagmanager cmp audit https://staging.example.com --format json -o cmp.json

pytagmanager cmp audit https://staging.example.com \
  --consent-action reject \
  --authorize-consent-interaction \
  --reload-after-consent
```

The report has stable rule IDs, confidence, evidence, remediation, and explicit
limitations. It does not produce a compliance score, does not decode most vendor
cookies, and never treats a banner as proof of enforcement. Cookie values and
request query strings are not serialized. See
[`docs/CMP_AUDIT.md`](docs/CMP_AUDIT.md) and
[`schemas/cmp/v1/audit-report.schema.json`](schemas/cmp/v1/audit-report.schema.json).
