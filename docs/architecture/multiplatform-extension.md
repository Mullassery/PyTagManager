# Multi-Platform Extension: Implementation Assessment

Status: implementation in progress. This document records what is implemented,
what is only locally verified, and what remains blocked. It is not a production
readiness claim.

## 1. Existing capabilities to preserve

The extension is additive to the existing PyTagManager repository:

- Rust crawler, semantic DOM graph, tracked-surface diffing and PyO3 bindings.
- Python recommendation, export, dictionary, diagnostics, site-wide reporting,
  snapshots and existing CLI commands.
- `control/` revisions, environments, validation, activation, rollback,
  checksums, file permissions and append-only audit records.
- Existing tests, packaging, CI and license. No feature was replaced to make the
  new code easier to build.

Phase 3 control-plane work was completed before this extension: `audit_event`
schema support, monotonic audit sequence numbers, environment activation and
rollback with `expected_current`, protected-environment approval, revision diffs,
and `environment`/`container audit`/`config diff` CLI commands.

## 2. Missing capabilities and module boundaries

| Area | Boundary | Current state |
| --- | --- | --- |
| Event contract | `schemas/events/v1/`, `python/pytagmanager/events/` | Implemented and tested |
| Public configuration | `schemas/container/v1/`, `distribution/public_config.py` | Implemented and tested |
| CDN publication | `python/pytagmanager/distribution/publisher.py`, `cdn` CLI | Implemented and tested on filesystem |
| Collection/validation | `python/pytagmanager/ingest/service.py` | Implemented and tested |
| Collection HTTP | `python/pytagmanager/ingest/http.py`, `serve-ingest` | Implemented and tested with loopback HTTP |
| PyTagShield adapter | `python/pytagmanager/ingest/pytagshield.py` | Implemented against documented ingest shape; production integration unverified |
| Web SDK | `sdk/web/` | Implemented, built, 11 tests pass |
| iOS SDK | `sdk/ios/` | Foundation-only Swift package; library builds and 19 executable checks pass; XCTest target expanded but requires Xcode/CI |
| Android SDK | `sdk/android/` | Implemented; Gradle 8.14.6/JDK 21/compileSdk 35 build passes with lint and 28 JUnit tests (debug + release); no emulator/device tests |
| Diagnostic rules | existing `diagnostics/` | Preserved; new SDK/event diagnostics added |
| GTM container inspection/import/export | `python/pytagmanager/gtm/`, `gtm` CLI | Implemented and tested for JSON/YAML; GTM semantics are best-effort and labeled |

The administrative control plane, publication tree, public CDN artifacts and
collection endpoint are separate. Clients never receive destination configs,
secret references or administrative credentials.

## 3. Data contracts

### Event contract v1

`schemas/events/v1/event.schema.json` and `batch.schema.json` define:

- `schema_version`, UUIDv4 `event_id`, bounded `event_name`, UTC RFC3339 `Z`
  timestamp, source platform/SDK name/version, public `container_id`.
- Optional consent purposes, source, provenance and `updated_at`; subject and
  correlation metadata; optional `config_version`; bounded JSON properties.
- Strict unknown-field rejection, 32 KiB event limit, sensitive-key denylist,
  24-hour clock-skew window (server side), batch size 1–100.

Fixtures are shared by Python, Web, iOS and Android checks.

### Public configuration

`schemas/container/v1/published-config.schema.json` defines a secret-free,
immutable document containing event allowlists/purposes, public tag and
destination metadata, compatibility, cache policy and an SHA-256 self-checksum.
It deliberately excludes tag parameters, destination configuration and secret
references. The checksum detects transit corruption; it does not authenticate a
publisher.

### Collection and PyTagShield

`POST /api/v1/events` accepts either an event or `{ "schema_version": "1.0",
"events": [...] }`. Responses return status, event id/name, retryability and
sanitized forwarding outcomes; event properties are not echoed. PyTagShield
forwarding maps to its documented ingest shape:

```json
{"event":"purchase","distinct_id":"user-42","timestamp":1760988123000,
 "properties":{"currency":"EUR"},"consent":{"analytics":true}}
```

The adapter sends the PyTagManager event id and correlation ids as headers. It
does not follow redirects, uses bounded timeouts, supports an optional
`env:`/`file:` bearer-token reference, and rejects private/loopback PyTagShield
URLs unless an operator explicitly opts in. Client consent is passed as input;
PyTagShield remains responsible for server policy and forwarding.

Dedupe defaults to a bounded in-memory cache. `--dedupe-db FILE` selects a
file-backed SQLite store in WAL mode so claims survive restarts and are shared
by collector processes on one host. The store contains only event ids, state
and expiry. It is not a distributed lock, and a direct write to PyTagShield
still bypasses collector dedupe.

## 3a. GTM debugging and same-domain event flow

`gtm inspect` performs deterministic checks against a GTM JSON/YAML container
snapshot: missing triggers, dangling trigger references, undefined variables,
duplicate tag/trigger names, duplicate GA4 event delivery, duplicate measurement
IDs and unused/paused objects. Findings include severity, confidence, evidence
and remediation. `gtm export` writes a GTM-compatible snapshot from a managed
revision; `gtm import` creates a draft revision and reports every GTM construct
it cannot represent. Import never activates.

For same-domain debugging, browser and server events should use one public
origin such as `https://www.example.com/collect`, backed by `serve-ingest`.
The PyTagManager collector validates and deduplicates by `event_id` before
forwarding to PyTagShield; PyTagShield applies consent/policy and forwards
eligible events to Meta, Google and other destinations.

**Duplicate-ID limitation:** PyTagShield 0.2.0 generates its own event ID and
does not accept the client event ID as its internal idempotency key. Direct
server ingestion into PyTagShield bypasses the collector's dedupe. End-to-end
duplicate suppression therefore requires all relevant events to pass through
the same collector, or a shared idempotency store / PyTagShield-side change.
Do not claim more than that.

## 4. CDN publication and caching

The filesystem publisher writes:

- `/containers/<container-key>/revisions/<config-version>/config.json` and
  `.sha256` (immutable, one-year cache).
- `/containers/<container-key>/environments/<slug>/latest.json` (no-cache,
  revision-checked pointer).
- `/containers/<container-key>/manifest.json` and `/index.json`.
- `/sdk/web/<version>/pytagmanager.js` and `.sha256`.
- `_headers.json` and `CACHE-POLICY.md` for self-hosting.

Publication validates the active revision, is atomic per file, records revision
history, and reuses existing immutable bytes when the same config version is
republished. No external CDN API is called. Rollback performs the control-plane
rollback and then republishes; the two writes are intentionally separate.

## 5. Security properties and limitations

Implemented:

- Secret exclusion checks on public config, `0600` output for sensitive exports,
  no secrets in CDN artifacts.
- SSRF-resistant URL validation, no redirect following, bounded payloads and
  response reads, per-client token-bucket rate limiting, bounded in-memory or
  durable SQLite dedupe, non-reflective error responses and sanitized logs.
- Optional API token for server-to-server calls; CORS configurable; HTTPS
  required except explicit loopback/private deployment.
- Sensitive key rejection in Python, Web and mobile event validation.
- Consent withdrawal removes queued mobile events whose purposes intersect the
  withdrawal.
- Optional TLS on the collection server; HTTPS is still required at the edge.
- iOS lifecycle observer flushes on background/termination through a bounded
  background task; delivery remains best-effort. XCTest execution requires Xcode
  and is wired into a macOS CI job, but neither that job nor the iOS-simulator
  lifecycle test has run in this environment.

Limitations:

- Rate limiting remains in-process. Durable dedupe is available through
  `--dedupe-db`; SQLite dedupe is single-host and is not a distributed lock.
  Multi-host deployments need shared routing or a shared idempotency service.
- The collection endpoint acknowledges validated events even without a
  forwarder. That is not delivery proof.
- CDN integrity does not authenticate a publisher and is not a substitute for
  TLS or authorization.
- CLI `cdn rollback` can leave control-plane and publication states out of sync
  if publishing fails after rollback. Re-run `pytagmanager cdn publish`.
- No automatic TLS certificate management; use a reverse proxy or `--tls-cert`.
- No real CDN provider or live PyTagShield control-plane API is available, so
  those integrations are contract-tested locally, not production-verified.

## 6. Verification evidence

Commands run in this environment:

```text
.venv-test/bin/python -m pytest -q
637 passed, 6 skipped

.venv-test/bin/python -m pytest tests/python/test_distribution.py \
  tests/python/test_ingest.py tests/python/test_gtm.py -q
35 passed

node --test sdk/web/test/sdk.test.js
11 passed

swift build --package-path sdk/ios
Build complete

swift run --package-path sdk/ios PyTagManagerChecks
PASS 19 Swift checks

cd sdk/android && ./gradlew :sdk:build
BUILD SUCCESSFUL
28 Android JUnit tests passed (debug and release), lint passed, debug/release AARs built

maturin build --release
fresh venv + pip install dist/*.whl
pytagmanager --help
installed FilesystemCDN.publish_environment -> sdk/web/0.1.0/pytagmanager.js
```

The wheel install check found and fixed two packaging defects: base CLI imports
no longer pull in optional `yaml`/Playwright dependencies, and the built wheel
now bundles the Web SDK asset instead of relying on an untracked `sdk/web/dist`
directory outside the package.

Swift `XCTest` cannot run because only Apple Command Line Tools are installed
(no Xcode); the executable Swift checks are the actual executed evidence.
Android was built with JDK 21, Gradle 8.14.6 and compileSdk 35. Its verification
is JVM unit tests only; no emulator or physical-device instrumentation tests
were run.

## 7. Phased plan and acceptance criteria

Completed in this pass: event contract, public config, filesystem CDN, Web SDK,
collection service/HTTP, durable single-host dedupe, PyTagShield adapter, iOS
Foundation SDK/lifecycle observer, Android SDK build/lint/JUnit validation
including auto-flush, and a wheel build/install smoke test.

Remaining:

1. iOS XCTest run in an Xcode environment, including the UIKit lifecycle test.
2. Android emulator or physical-device instrumentation tests.
3. Live PyTagShield/CDN integration and multi-host idempotency.

Acceptance for the extension:

- Existing Python/Rust tests and CLI behavior remain green.
- Web/iOS/Android validate the same shared event fixtures.
- Public configuration contains no secrets and fails closed on bad integrity.
- CDN publication is immutable, verifiable and rollback-aware.
- Collection rejects malformed/oversized/rate-limited events, deduplicates
  retries safely and never claims delivery without a forwarding outcome.
- PyTagShield integration uses only documented endpoints and clearly labels
  production compatibility as unverified until tested against a running instance.
