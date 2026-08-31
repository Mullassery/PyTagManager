# PyTagManager

[![CI](https://github.com/Mullassery/PyTagManager/actions/workflows/ci.yml/badge.svg)](https://github.com/Mullassery/PyTagManager/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](https://github.com/Mullassery/PyTagManager/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-pytagmanager-blue)](https://pypi.org/project/pytagmanager/)

An AI-native analytics implementation platform: crawl a website, build a
semantic DOM graph, generate tracking recommendations, export to seven
analytics/tag-management platforms, track how a site's tracking surface
changes over time, verify at runtime in a real browser that tracking
actually fires the way it should, and (optionally) classify business
intent with a local LLM — without hand-inspecting the DOM, writing CSS
selectors, or manually replaying click-throughs in GTM Preview mode.

**Current scope**: web crawling + semantic DOM graph (Rust) → rule-based
tracking recommendations (Python) → export to GTM, GA4, Segment, Snowplow,
Tealium, RudderStack, and Adobe Tags → crawl-to-crawl diffing → **Tracking
Observability & Diagnostics** (real-browser interaction → dataLayer → GTM
→ GA4 correlation and rule-based root-cause diagnosis) → optional
Ollama-backed AI intent classification. This is a deliberately scoped slice
of a much larger long-term vision — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full capability
table and what's deliberately deferred (visual AI, XDM modeling, an
enterprise audit engine, site-wide cross-page consistency analysis, and
non-web platforms — each with a specific reason, not a blanket "not yet").

## Architecture

- **Rust core** (`src/`, via [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs)): async crawler (link discovery, sitemap.xml, robots.txt, BFS with dedup) and a semantic DOM graph engine (XPath/CSS/stable-selector generation per element).
- **Python layer** (`python/pytagmanager/`): orchestration, rule-based tracking recommendations, exporters, crawl-snapshot diffing, an optional local-LLM intent classifier, and Tracking Observability & Diagnostics (`observability/`, `correlation/`, `diagnostics/`, `analytics_api/`, `reporting/`), built on top of the compiled Rust extension.

```
pytagmanager crawl <url>
        │
        ▼
  Rust: crawl + parse each page into a SemanticGraph
        │
        ▼
  Python: recommend_for_graph() — rule-based CTA/form detection
    (or, optionally: intent.OllamaIntentClassifier — local-LLM-backed)
        │
        ├──▶ export/{gtm,ga4,segment,snowplow,tealium,rudderstack,adobe_tags}.py
        │
        └──▶ version_control/snapshot.py — save a snapshot for `pytagmanager diff`
```

## Quickstart

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
(default `qwen2.5:0.5b`) instead of keyword matching:

```python
from pytagmanager.intent.ollama_classifier import OllamaIntentClassifier
from pytagmanager.intent.base import PageContext

classifier = OllamaIntentClassifier()  # talks to http://localhost:11434
result = classifier.classify(node, PageContext(url=page_url, page_title=title))
```

Requires `ollama serve` running locally with the model pulled (`ollama pull
qwen2.5:0.5b`). If Ollama isn't reachable, `classify()` falls back
automatically to the deterministic keyword heuristic rather than raising —
this runs entirely locally, with no cloud LLM API calls or credentials
required; see `docs/ARCHITECTURE.md` for where a future cloud-LLM-backed
classifier would plug in via the same `IntentClassifier` interface.

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
(`sitewide/anomalies.py`): a page firing an event far more than its
template's own observed average, or a page whose GTM container/GA4
measurement ID disagrees with the rest of its template — both computed
relative to what was actually observed, never a hardcoded threshold. Not
compatible with `--scenario` (site-wide aggregation needs a crawl of more
than one page). Cross-journey checks like duplicate-purchase detection
(the same `transaction_id` firing `purchase` more than once anywhere in
the session) run in both modes and appear as "Additional Findings".

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

### Privacy

Telemetry never leaves your machine unless you supply GTM/GA4 credentials
yourself. `events.redact_payload` strips values under obviously-sensitive
keys (password, token, secret, credit card, SSN, ...) before a
`TrackingEvent` is even constructed, and `diagnostics.rules.rule_pii_leak`
separately scans payload *content* (not just key names) for
email/phone/SSN/credit-card patterns that leaked through an innocuous
field name.

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
once before `pytest` if you haven't already (otherwise those tests fail
with a clear "install pytagmanager[diagnostics]" error at run time rather
than silently skipping).

macOS note: this repo includes `.cargo/config.toml` with the linker flags
PyO3 extension-module crates need for plain `cargo build`/`cargo test` to
work outside of maturin (maturin sets these automatically; raw `cargo`
doesn't).

## Known Issues

- No open GitHub issues and no `TODO`/`FIXME` markers in `src/` or
  `python/` as of this pass — the gaps that exist are the deliberately
  deferred phases tracked in `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`
  (visual/screenshot grounding, AI intent classification beyond the local
  Ollama fallback, multi-platform data-layer export, XDM modeling, the
  enterprise audit engine, and non-web platforms), not undocumented rot.
- `ClaudeIntentClassifier` referenced in `docs/ROADMAP.md`'s Phase 2 is
  planned, not implemented; `python/pytagmanager/intent/base.py`'s
  `IntentClassifier` protocol has only one real implementation today
  (`OllamaIntentClassifier`), plus the deterministic rule-based heuristics
  used by default.

## Project layout

```
Cargo.toml / pyproject.toml   # Rust crate + maturin/Python packaging
src/                          # Rust: crawler/ + dom/ (semantic graph, selectors)
python/pytagmanager/          # Python: discovery/ recommend/ intent/ export/ version_control/ cli.py
                               #         observability/ correlation/ diagnostics/ analytics_api/ reporting/ sitewide/
tests/python/                 # Python tests + HTML fixtures (Rust tests live next to their modules)
docs/ARCHITECTURE.md          # implemented vs. deliberately deferred, plus the full long-term spec
```
