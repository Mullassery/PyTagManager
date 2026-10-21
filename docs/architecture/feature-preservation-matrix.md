# PyTagManager — Feature Preservation Matrix

- **Status:** Phase 0 baseline. Every row is a protected capability.
- **Baseline commit:** `main` @ `92bc000`
- **Baseline test results:** 23 Rust tests passed; 419 Python tests passed,
  4 Ollama-dependent skipped; `cargo fmt --check` and
  `cargo clippy --all-targets -- -D warnings` clean.

This matrix is the regression contract for the platform evolution. A phase is
not complete if any "Protected behavior" below changes without an approved,
documented migration and an explicit regression test.

---

## 1. Protected capabilities

| # | Capability | Implementation location | Current behavior and interfaces | Existing tests / baseline | Planned additive extension | Required regression tests |
|---|---|---|---|---|---|---|
| 1 | **URL discovery, crawling, scraping** | `src/crawler/orchestrator.rs`, `src/crawler/sitemap.rs`, `src/lib.rs:47`; `discovery/crawl.py`; CLI `crawl` | Async BFS crawl, sitemap/robots, dedup, concurrency, max pages, retries, circuit breaker, rate limit, custom headers, SSRF guard, `crawl_status`, `--browser {off,auto,always}`, `--render` | `tests/crawl_integration.rs` (15), `test_core_ffi.py`, `test_cli.py`; green | Managed configurations may *reference* crawl results and drafts; crawler API and behavior remain unchanged. Optional control-plane metadata may be attached by callers, never required. | Same crawler suite must stay green; no network behavior or SSRF change without new tests; CLI `crawl` options remain backward-compatible |
| 2 | **Existing tag/script/pixel discovery** | `tagexec/static_scan.py`, `tagexec/duplicates.py`, `runtime/sniffer.py`, `observability/session.py`; CLI `scan-tags`, `diagnose --detect-duplicate-tags` | Detects GTM containers and 24+ vendor signatures from rendered DOM; runtime network sniffing; duplicate detection only when corroborated | `test_tagexec_static_scan.py`, `..._e2e.py`, `test_tagexec_duplicates.py`, `test_runtime_sniffer.py`, `test_scan_tags_cli.py` | Discovered items may be **converted into draft** managed tags after explicit validation/approval. No automatic conversion or publishing. | Static scan findings, vendor list, and duplicate rules unchanged; new conversion tests must prove drafts are not executable until approved |
| 3 | **Semantic DOM graph construction** | `src/dom/{parser,graph,selectors}.rs`; `_core.parse_html` | Node fields (tag, xpath, CSS, stable selector, text, ARIA, classes, attributes); selector priority; `find_by_tag`; used by render mode | Rust unit tests in `src/dom/`, `test_core_ffi.py`; green | Control-plane selectors may reference the same stable-selector vocabulary; no change to graph schema required | Graph field/shape tests; selector-priority tests; rendered-DOM ingestion tests |
| 4 | **Tracking-event discovery and recommendations** | `recommend/heuristics.py`, `recommend/models.py`; optional `intent/ollama_classifier.py`; CLI `crawl --intent` | Deterministic rule-based CTA/form discovery, stable selectors, rationales, confidence; optional local Ollama; heuristic fallback | `test_heuristics.py`, `test_intent_ollama.py`; green (Ollama tests skip when absent) | Recommendations become one **source** for draft tags; managed tags are a separate, approved model. New `to_draft()` transformation must preserve source evidence. | Existing recommendation output tests unchanged; new tests must assert observed recommendations ≠ approved managed tags |
| 5 | **Configuration generation and export** | `export/base.py` registry; `export/{gtm,ga4,segment,snowplow,tealium,rudderstack,adobe_tags}.py`; `_taxonomy.py`; CLI `crawl --export` | Seven export formats; CLI choices generated from `EXPORTERS`; deterministic JSON-shaped artifacts | `test_exporters.py` (20), `test_gtm_export.py`, `test_cli.py`; green | Managed configs gain adapters that can emit the same existing formats and new server-side envelopes. Existing output shapes must remain byte-compatible for unchanged inputs. | Golden/snapshot tests for all seven exporters; registry/CLI choice test; explicit test that new adapters do not alter legacy output |
| 6 | **Real headless-browser runtime verification** | `observability/session.py`, `agent.js`; `correlation/journey.py`; `diagnostics/rules.py`; CLI `diagnose`; `runtime/`; `perf/` | Real Playwright Chromium; capture interaction/dataLayer/GTM/network/state; 11 deterministic rules; traces; site-wide QA; performance isolation | `test_observability_*`, `test_correlation.py`, `test_diagnostics_rules.py`, `test_diagnose_*`, `test_runtime_*`, `test_perf_*`, `test_sitewide_*`; **419 passed total** | Published configurations gain a verification path using the same session/agent. Preview adds a Python execution trace; browser verification remains real, never mocked. | Browser tests must run against real Chromium in CI; no replacement with mocks; new published-config verification must assert real network/DOM evidence, and distinguish client vs server evidence |
| 7 | **Existing CLI commands and public APIs** | `python/pytagmanager/cli.py`; `python/pytagmanager/__init__.py` | 8 commands: `crawl`, `diff`, `dictionary`, `diagnose`, `gtm-plan`, `scan-tags`, `perf`, `lighthouse`; curated exports listed in current-state doc | `test_cli*.py`, `test_core_ffi.py`; green | Additive commands (e.g. `container`, `config`, `publish`, `integration`) and additive exports. No rename/removal of existing commands/options. | CLI help/smoke tests; import-surface tests; explicit deprecation policy only with approval |
| 8 | **Existing configuration formats and integrations** | Snapshot v1 (`version_control/snapshot.py`); export formats; GTM read-only client (`analytics_api/gtm_client.py`); webhook alert shape (`sitewide/notify.py`) | JSON snapshot v1; seven export formats; GTM Management API read-only; Slack-compatible `{"text": ...}` webhook | `test_version_control.py`, `test_exporters.py`, `test_analytics_api_clients.py`, `test_notify_backoff.py`; green | New envelope/schema versions are **parallel** formats. Existing formats can be imported/transformed explicitly. | Format-compatibility tests; import/export round-trip tests; no silent field removal |
| 9 | **Tests, CI, packaging, dependencies, license compatibility** | `.github/workflows/ci.yml`, `pyproject.toml`, `Cargo.toml`, `LICENSE`; pytest/cargo suites | Rust fmt/clippy/tests; Python 3.12, maturin, Playwright Chromium, narrow ruff gate, pytest; cargo/pip audit; Apache-2.0 | CI definitions inspected; local equivalent green | New functionality must extend this CI without weakening gates; new deps need justification and audit | CI must keep fmt/clippy/pytest green; no test deletion or assertion weakening; packaging must still build; license remains Apache-2.0 |

---

## 2. Distinctions that must never be collapsed

| Distinction | Preserve as |
|---|---|
| Crawled/observed tracking vs. managed configuration | Separate models and APIs. Discovery can create **drafts**; only validated/approved revisions are publishable. |
| Export generation vs. live deployment | Exporters produce artifacts. Publishing is an explicit, audited operation. No exporter may deploy. |
| Browser-side execution vs. server-side execution | Separate capability flags, adapters, evidence, and UI/report labels. |
| Runtime verification vs. synchronization acknowledgement | An ack proves the receiver accepted a revision, not that a downstream event was delivered. |
| Recommendation event labels vs. vendor event names | Existing recommendation taxonomy stays; adapters map explicitly and document uncertainty. |
| Public identifiers vs. credentials | `container_id`/`integration_id`/`config_version` are identifiers, never auth secrets. |
| Existing crawl snapshot diff vs. configuration revision control | Keep `SNAPSHOT_FORMAT_VERSION = 1` behavior; add a separate immutable revision store. |

---

## 3. Required regression gates per phase

Every phase must run, at minimum:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
pytest tests/python -v
```

Additional gates:

- **Phase 1:** identity persistence, duplicate import, clone, restart,
  schema validation, checksum determinism, atomic-write/lock behavior.
- **Phase 2:** trigger/variable evaluation, malformed configs, consent-denied
  behavior, redaction, adapter validation, draft-vs-approved separation.
- **Phase 3:** revision immutability, diff, environment isolation,
  concurrent-edit conflict detection, authorized publish/rollback, audit
  completeness, no automatic production publish in tests.
- **Phase 4:** idempotency, duplicate requests, lost acknowledgements,
  bounded retries/timeouts, reconciliation, incompatible schema, integration
  ID stability, ack-vs-delivery boundary.
- **Phase 5:** real-browser verification of published configs; explicit
  client/server evidence split; no mock presented as vendor compatibility.
- **Phase 6:** SSRF/destination allowlist negative tests, secret redaction,
  authorization failures, tenant isolation, malformed/oversized input,
  clean-environment install, docs accuracy.

---

## 4. Stop conditions (report before proceeding)

Stop and report a conflict if a proposed change would:

1. Replace or bypass the MudFish-backed crawler, or weaken its SSRF guard.
2. Replace real browser verification with mocks or remove Chromium tests.
3. Make PyTagShield or the new control plane mandatory for crawl, discovery,
   export, or browser verification.
4. Change an existing exporter's output shape, CLI option, or public Python
   symbol incompatibly without explicit approval.
5. Delete, skip, or weaken an existing test to make a new phase pass.
6. Publish/activate a production configuration automatically during
   development or tests.
7. Claim PyTagShield compatibility, benchmarks, or security guarantees that
   have not been verified against the real contract.
8. Use a mutable field (name, URL, content hash) as the sole stable identity.
9. Treat a public integration/container ID as a credential.
10. Put private credentials in browser-delivered assets or public exports.

---

## 5. Baseline evidence

- Full Python suite: `.venv-test/bin/python -m pytest tests/python -q` →
  `419 passed, 4 skipped in 210.39s`.
- Rust: `cargo test` → 8 unit + 15 integration passed.
- Formatting/lint: `cargo fmt --check` exit 0; `cargo clippy --all-targets
  -- -D warnings` exit 0.
- Skips: 4 Ollama-dependent tests; no tests were modified or disabled for
  this audit.
