## What changed and why

<!-- Link the roadmap phase (docs/ROADMAP.md) or issue this relates to, if any. -->

## Testing

<!-- What did you actually run? Paste real command + output/pass-fail, not "tests pass". -->

- [ ] `cargo fmt --check` / `cargo clippy --all-targets -- -D warnings` (Rust changes only)
- [ ] `cargo test` (Rust changes only)
- [ ] `pytest tests/python -v` (Python changes only — note if you ran the full suite or a subset)

## Documentation

- [ ] Updated `README.md` / `../docs/internal/ROADMAP_HONEST.md` / `docs/` if this changes what's built, tested, or working
- [ ] Did not describe untested code as working, and did not soften a known limitation (see `CONTRIBUTING.md`'s documentation honesty policy)

## Checklist

- [ ] No secrets/credentials committed
- [ ] No new `TODO`/`FIXME` left without an issue reference or explicit scope note
