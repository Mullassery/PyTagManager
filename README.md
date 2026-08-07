# PyTagManager

An AI-native analytics implementation platform: crawl a website, build a
semantic DOM graph, generate tracking recommendations, and export a
ready-to-review GTM container — without hand-inspecting the DOM or writing
CSS selectors by hand.

**v1 scope**: web crawling + semantic DOM graph (Rust) → rule-based tracking
recommendations + GTM export (Python). This is a deliberately scoped first
slice of a much larger long-term vision — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for what's implemented today
versus the full roadmap (visual AI, runtime behavior capture, LLM-based
intent classification, XDM modeling, an audit engine, and non-web
platforms).

## Architecture

- **Rust core** (`src/`, via [PyO3](https://pyo3.rs)/[maturin](https://www.maturin.rs)): async crawler (link discovery, sitemap.xml, robots.txt, BFS with dedup) and a semantic DOM graph engine (XPath/CSS/stable-selector generation per element).
- **Python layer** (`python/pytagmanager/`): orchestration, rule-based tracking recommendations, and exporters, built on top of the compiled Rust extension.

```
pytagmanager crawl <url>
        │
        ▼
  Rust: crawl + parse each page into a SemanticGraph
        │
        ▼
  Python: recommend_for_graph() — rule-based CTA/form detection
        │
        ▼
  Python: build_gtm_container() — GTM JSON export
```

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install maturin pytest
maturin develop          # builds the Rust extension, installs pytagmanager editable

pytagmanager crawl https://example.com --max-pages 20 --export gtm -o out.json
```

## Development

```bash
cargo test               # Rust unit tests (selectors, robots.txt, sitemap parsing, DOM parsing)
pytest tests/python -v   # Python tests (heuristics, GTM export)
```

macOS note: this repo includes `.cargo/config.toml` with the linker flags
PyO3 extension-module crates need for plain `cargo build`/`cargo test` to
work outside of maturin (maturin sets these automatically; raw `cargo`
doesn't).

## Project layout

```
Cargo.toml / pyproject.toml   # Rust crate + maturin/Python packaging
src/                          # Rust: crawler/ + dom/ (semantic graph, selectors)
python/pytagmanager/          # Python: discovery/ recommend/ intent/ export/ cli.py
tests/python/                 # Python tests + HTML fixtures (Rust tests live next to their modules)
docs/ARCHITECTURE.md          # v1-implemented vs. planned, plus the full long-term spec
```
