# PyTagManager

[![CI](https://github.com/Mullassery/PyTagManager/actions/workflows/ci.yml/badge.svg)](https://github.com/Mullassery/PyTagManager/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.1.2-blue)](https://github.com/Mullassery/PyTagManager/releases)
[![License](https://img.shields.io/badge/license-Proprietary-blue)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-pytagmanager-blue)](https://pypi.org/project/pytagmanager/)

An AI-native analytics implementation platform: crawl a website, build a
semantic DOM graph, generate tracking recommendations, export to seven
analytics/tag-management platforms, track how a site's tracking surface
changes over time, and (optionally) classify business intent with a local
LLM — without hand-inspecting the DOM or writing CSS selectors by hand.

**Current scope**: web crawling + semantic DOM graph (Rust) → rule-based
tracking recommendations (Python) → export to GTM, GA4, Segment, Snowplow,
Tealium, RudderStack, and Adobe Tags → crawl-to-crawl diffing → optional
Ollama-backed AI intent classification. This is a deliberately scoped slice
of a much larger long-term vision — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full capability
table and what's deliberately deferred (visual AI, runtime behavior
capture, XDM modeling, an enterprise audit engine, and non-web platforms —
each with a specific reason, not a blanket "not yet").

## Architecture

- **Rust core** (`src/`, via [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs)): async crawler (link discovery, sitemap.xml, robots.txt, BFS with dedup) and a semantic DOM graph engine (XPath/CSS/stable-selector generation per element).
- **Python layer** (`python/pytagmanager/`): orchestration, rule-based tracking recommendations, exporters, crawl-snapshot diffing, and an optional local-LLM intent classifier, built on top of the compiled Rust extension.

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

## Development

```bash
cargo test               # Rust unit tests (selectors, robots.txt, sitemap parsing, DOM parsing)
pytest tests/python -v   # Python tests (heuristics, exporters, diffing, intent classification)
```

macOS note: this repo includes `.cargo/config.toml` with the linker flags
PyO3 extension-module crates need for plain `cargo build`/`cargo test` to
work outside of maturin (maturin sets these automatically; raw `cargo`
doesn't).

## Known Issues

- No open GitHub issues and no `TODO`/`FIXME` markers in `src/` or
  `python/` as of this pass — the gaps that exist are the deliberately
  deferred phases tracked in `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`
  (runtime/visual grounding, AI intent classification beyond the local
  Ollama fallback, multi-platform data-layer export, XDM modeling, the
  audit engine, and non-web platforms), not undocumented rot.
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
tests/python/                 # Python tests + HTML fixtures (Rust tests live next to their modules)
docs/ARCHITECTURE.md          # implemented vs. deliberately deferred, plus the full long-term spec
```
