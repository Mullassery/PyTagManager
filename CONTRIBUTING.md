# Contributing to PyTagManager

## Before you start

Read [`README.md`](README.md) for what's actually built and working, and
[`docs/VISION.md`](docs/VISION.md) + [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for where the project is going and why. [`ROADMAP_HONEST.md`](ROADMAP_HONEST.md)
is the current source of truth on what's shipped vs. not — check it before
assuming a feature is missing or already exists.

This is a solo-maintained project (see [`SECURITY.md`](SECURITY.md) for
response-time expectations). There is no dedicated maintainer team, no SLA on
PR review, and no guarantee a given contribution will be merged.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install maturin pytest
maturin develop          # builds the Rust extension, installs pytagmanager editable

# Tracking Observability / Diagnostics / Dictionary / Perf tests need the
# diagnostics extra + a Chromium binary:
pip install -e '.[diagnostics]'
playwright install chromium
```

macOS note: raw `cargo build`/`cargo test` (outside `maturin`) need the
linker flags in `.cargo/config.toml` for PyO3 extension-module crates to
link. `maturin develop`/`maturin build` set these automatically; if you
invoke `cargo` directly and it fails to link, that's why.

## Running the test suite

```bash
cargo test               # Rust: crawler, sitemap/robots parsing, DOM/selectors
pytest tests/python -v   # Python: heuristics, exporters, diffing, observability, etc.
```

Most of the Python suite drives a real headless Chromium instance (no
mocked browser behavior) — expect it to be slower than a typical unit-test
suite, and make sure `playwright install chromium` has been run once.

Before submitting a change to Rust code, also run:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
```

CI runs all of the above; a PR that fails any of them won't pass CI.

## Making a change

1. Fork the repo and create a branch off `main`.
2. Make your change with tests. A change with no test coverage for the
   behavior it adds or fixes will generally not be merged — this project's
   honesty policy (see below) depends on test coverage actually reflecting
   what's claimed to work.
3. Run the full validation above locally before opening a PR.
4. Open a PR describing what changed and why. Reference the roadmap phase
   or issue it relates to, if any.

## Documentation honesty policy

This project's docs (`README.md`, `ROADMAP_HONEST.md`, `docs/`) are
maintained to a specific, deliberately blunt standard: no hedging on
project status. If something isn't built, the docs say "not built," not
"planned" or "may be added." If something is untested, the docs say so
explicitly rather than describing it as working. PRs that add a feature
should update the relevant doc section to match this standard — don't
describe a new feature as more complete or more tested than it actually is,
and don't soften a known limitation to make a PR look more finished.

## Code style

- **Rust**: `cargo fmt` (default settings) + `cargo clippy` clean, no
  suppressed lints without a comment explaining why.
- **Python**: no enforced formatter is wired into CI yet (see
  `ROADMAP_HONEST.md` for other CI gaps); match the existing style in the
  file you're editing. Type hints are used throughout `python/pytagmanager/`
  — new code should include them.

## Reporting bugs / requesting features

Use the issue templates under `.github/ISSUE_TEMPLATE/`. For security
issues, do not open a public issue — see [`SECURITY.md`](SECURITY.md).

## License

By contributing, you agree your contributions are licensed under this
project's [Apache-2.0 license](LICENSE).
