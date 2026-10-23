# Ecosystem Integration — PyTagManager

- **Status:** Evidence-backed integration baseline, reviewed 2026-10-22; cross-repo blocker summary added 2026-10-23.
- **Repository:** PyTagManager (`Mullassery/PyTagManager`).
- **Scope:** This repository only. No sibling repository was modified.
- **Authority:** Source, schemas, tests and executable results below. README
  claims without executable evidence are marked as such.

## A. Repository role and boundaries

PyTagManager owns browser/GTM tagging diagnosis, CMP/consent auditing, runtime
verification, script-performance evidence and reviewable configuration
artifacts. It produces evidence and draft configuration; it does not own
customer profiles, segmentation, activation, CRM records or destination
routing.

| Concern | Owner |
|---|---|
| Crawl/fetch and rendered web intelligence | MudFish (consumed) |
| Tag discovery, QA, CMP audit, GTM/container inspection | PyTagManager |
| Server-side consent, minimization, routing and delivery | PyTagShield |
| CDP identity, profiles, audiences, journeys | PyCustomerHub |
| Segmentation/scoring | ClusterAudienceKit |
| Reverse ETL/activation and PII masking | PyReverseETL |
| CRM records/RBAC/webhooks | Squid-CRM |
| Alternative Rust-native fetching/extraction | QuillSift (not used) |

PyTagManager must remain standalone-usable without PyTagShield or any other
ecosystem service. No sibling package is a mandatory dependency.

## B. Real gaps to call out

These are unresolved gaps, stated only at the level the evidence supports.
**Tested** means an exact command was run; **source-inspected** means static
reading only; **unverified** means no executing test exists. Details are in
sections G and H.

1. **PyTagShield control-plane integration is blocked.** Source inspection of
   the audited 0.2.0 tree found no supported registration/config/activation/
   rollback API. No live control-plane endpoint was tested.
2. **There is no PyCustomerHub adapter.** Source inspection found a different
   `POST /events` envelope; no live PyCustomerHub call was made. Event v1 carries
   no tenant/schema-ref/identity-array fields. No compatibility is claimed.
3. **Multi-tenant collection safety is unverified.** Optional auth, CORS `*`
   default, per-event batch accounting, opt-in trusted-proxy identity and SQLite
   dedupe are implemented. Local HTTP tests cover forwarding-header spoofing and
   batch token accounting, but no live proxy, abuse, multi-host or tenant test
   was run.
4. **Consent authority is not verified end-to-end.** PyTagManager forwards the
   client consent map and does not enforce consent. No live PyTagShield policy
   test was run, so this must not be described as tamper-proof consent.
5. **Exactly-once forwarding is unverified.** Dedupe is SQLite-backed and
   completion is recorded after forwarding by code inspection; no crash/retry
   test exists.
6. **SSRF resistance is unverified.** URL validation and urllib resolution are
   separate (code inspection); no DNS-rebinding/TOCTOU test exists.
7. **Counterpart PyTagShield security is unverified.** Source inspection noted
   optional ingest auth and no visible outbound destination allowlist. No live
   PyTagShield security test was run; treat these as source-review findings.
8. **Mobile verification is incomplete here.** Web tests and Swift checks were
   executed. iOS XCTest failed on this machine and Android was not run because
   no SDK/emulator is configured.
9. **PyTagShield 0.2.0 has a packaging gap.** PyPI publishes only a macOS arm64
   wheel (`cp310-abi3-macosx_11_0_arm64`); an attempted Linux-wheel resolution
   failed and no sdist is listed. The contract CI job therefore runs on macOS.
10. **Historical docs contain superseded claims.** Banners were added to the
   older audit/current-state docs; the claims were not re-tested in this pass.

## C. Integration matrix

Statuses: **VERIFIED**, **PARTIAL**, **MISSING**, **BLOCKED**, **NOT APPLICABLE**.

| Integration | Direction | Public interface and evidence | Status | Gap / blocker |
|---|---|---|---|---|
| MudFish crawler crates | consume | `Cargo.toml` pins `mudfish-core/frontier/fetch/parser/browser` to git tag `rust-v0.1.3`; `Cargo.lock` pins commit `fd308a9`; `src/crawler/orchestrator.rs`, `tests/crawl_integration.rs` | **VERIFIED** | None for the pinned contract. Upgrade is deliberate and tag-based. |
| PyTagShield static config | produce | `control/pytagshield.py:project_to_pytagshield`; `config pytagshield-export`; `tests/python/test_control_pytagshield.py`; output accepted by real `pytagshield==0.2.0` `Config.from_yaml` and routed through `Pipeline.process` | **VERIFIED** | Not a 1:1 tag/trigger projection; unsupported semantics fail closed or warn. |
| PyTagShield event forwarding | produce | `ingest/pytagshield.py:to_pytagshield_event` / `PyTagShieldClient`; `POST /api/v1/event`; `tests/python/test_ingest.py`; mapped event accepted by real `pytagshield==0.2.0` pipeline; local HTTP server verifies wire shape | **PARTIAL** | No live PyTagShield HTTP server/deployment test. The local server is a contract double, not delivery proof. |
| PyTagShield control plane | produce | Source inspection found no registration/upload/activate/ack/effective endpoint in the audited 0.2.0 tree; contract is documented as provisional | **BLOCKED / unverified live** | Counterpart control plane not identified. Do not add an invented live client. |
| PyCustomerHub ingestion | produce | Source inspection of PyCustomerHub's `crates/api/src/routes/events.rs` found `POST /events` with `EventEnvelope` fields `tenant_id`, `schema{name,version}`, `identity[]`, `data`, `source{type,name}`; no live call was made | **BLOCKED / unverified live** | Cross-repo blocker: OCDS envelope vs Squid envelope v1, no schema registration, and no write-key auth on the edge gateway. PyTagManager event v1 also lacks tenant/schema-ref/identity-array fields. No adapter was invented. |
| ClusterAudienceKit | none | No customer scores/segments are produced or consumed | **NOT APPLICABLE for core / OPEN with Squid** | Segmentation belongs to ClusterAudienceKit. Segment custom-object schema remains open; PyTagManager does not define the segment contract. |
| PyTagManager findings → Squid | produce | `python/pytagmanager/squid/findings.py`; `pytagmanager squid manifest|findings`; `schemas/squid/v1/tag-finding.schema.json`; `tests/python/test_squid_findings.py` | **PARTIAL / proposed contract** | Versioned `tagManagerFinding` object, record schema and lookup/upsert plan defined. Squid has not accepted the metadata, no live write was run, and no credentials are bundled. |
| PyReverseETL | none | Collection deliberately does not perform activation or destination routing | **NOT APPLICABLE for core / BLOCKED with Squid** | Activation/CRM sync belongs to PyReverseETL/PyTagShield. Squid integration is blocked on an `Idempotency-Key` header and a per-record payload contract. |
| Squid-CRM | none | No customer-record or RBAC contract exists here | **BLOCKED for writes / NOT APPLICABLE for core** | No write-key auth on the edge gateway and no schema registration for the blocked PyCustomerHub/PyReverseETL paths. CRM ownership stays in Squid-CRM. |
| PyTagShield → Squid records | produce/consume | No live or contract-tested record path exists; audited PyTagShield server binary was a no-op | **UNVERIFIED / OPEN** | Consent attachment semantics are unresolved: records vs events vs both. Do not treat this as a supported delivery path. |
| QuillSift | none | PyTagManager delegates crawl/fetch to MudFish; no QuillSift dependency or adapter | **NOT APPLICABLE** | Adding a second crawler path would duplicate MudFish and create conflicting SSRF/budget semantics. |
| Internal Web/Android/iOS SDKs | produce/consume | Shared event v1 schema and fixtures in `schemas/events/v1/`; Web SDK and Swift checks pass | **PARTIAL** | Android build/device tests and iOS XCTest are unavailable in this environment; both must run in CI or a developer environment. |

## D. Implemented changes in this pass

1. **PyTagShield response correctness**
   - `python/pytagmanager/ingest/pytagshield.py`: response body status is now
     authoritative. A local HTTP contract test covers HTTP 202 with
     `status: "rejected"`; it is no longer reported as forwarded.
   - Tests cover accepted, rejected, backpressure and missing/unknown responses.
     `partially_accepted` uses the same forwarding branch as `accepted`.
   - No live PyTagShield HTTP server was run. The claim is about the adapter's
     tested response handling, not the live server's status codes.

2. **Anonymous identity isolation**
   - Events without `subject.id` now map to `anon:<event_id>` instead of the
     shared `_anonymous` identifier. Retries of the same logical event keep the
     same fallback; unrelated anonymous events no longer collapse into one
     PyTagShield distinct ID/consent record.

3. **Contract tests**
   - Added local-HTTP tests for rejected and unknown response statuses.
   - Added an optional real-PyTagShield pipeline test for mapped events.
   - Added an optional real-PyTagShield projection/routing test covering allowed
     and denied consent.

4. **Dependency security**
   - Updated `Cargo.lock` within existing semver ranges for
     RUSTSEC-2026-0381/0382/0383: `rustls-webpki` 0.103.16,
     `webpki-roots` 1.0.10 and `webpki-root-certs` 1.0.10.
   - No `Cargo.toml` requirement was changed. Rust tests, fmt, clippy and
     `cargo audit` pass after the update. A stale `certifi` in the local test
     environment was updated separately; it is not a project dependency.

5. **Documentation**
   - Updated `docs/architecture/pytagshield-integration.md` with the implemented
     event data plane, fail-closed response semantics, anonymous fallback and
     the still-missing control plane.
   - Added this integration matrix and the security/gap register below.

## E. Contracts and version assumptions

Statements here come from source/schema inspection unless explicitly tied to a
test result in section F. They describe interfaces, not live compatibility.
- **PyTagManager event contract:** `schemas/events/v1/event.schema.json`,
  `schema_version: "1.0"`, UUIDv4 event ID, RFC 3339 UTC timestamp, strict
  unknown-field rejection, 32 KiB event limit, sensitive-property denylist.
- **PyTagShield:** audited at workspace version `0.2.0`, git checkout `682f4ab`.
  Consumes `POST /api/v1/event` with `event`, `distinct_id`, `timestamp` (ms),
  `properties`, optional boolean `consent`. Response `status` is one of
  `accepted`, `partially_accepted`, `backpressure`, `rejected`. PyPI 0.2.0
  publishes only a macOS arm64 wheel and no sdist; Linux must build from a
  source checkout.
- **PyTagShield configuration:** strict startup YAML; no runtime config-sync API.
  PyTagManager emits YAML-compatible JSON and optionally validates it with the
  installed Python binding. `pytagshield.control.v1` remains a proposal.
- **MudFish:** Rust crates pinned to tag `rust-v0.1.3`; no private imports.
- **PyCustomerHub:** public `POST /events` observed at repository commit
  `e79f235`; its envelope is not compatible with PyTagManager event v1 without
  an explicit mapping/configuration layer. No compatibility claim is made.
- **No new shared package or universal schema was introduced.** Existing
  boundaries remain owned by the respective repositories.

## F. Test commands and actual results

Environment: `.venv-test/bin/python` (CPython 3.12.13), macOS arm64. Optional
`pytagshield==0.2.0` was installed only in this test environment to run the
native contract checks; it is not a PyTagManager dependency.

| Command | Result |
|---|---|
| `pytest tests/python/test_ingest.py -q` | **34 passed** |
| `pytest tests/python/test_squid_findings.py -q` | **9 passed** |
| `pytest tests/python/test_sdr.py -q` | **13 passed** |
| `pytest tests/python/test_control_pytagshield.py -q` | **20 passed** (native validation and routing executed) |
| `cargo test --workspace -q` | **23 passed** (8 unit, 15 integration) |
| `cargo fmt --check` / `cargo clippy --all-targets -- -D warnings` | **passed** |
| `cargo audit` | **passed**, 339 dependencies; 3 advisories fixed by lockfile update |
| `pytest -q` (full Python suite) | **737 passed, 4 skipped** |
| `ruff check --select E9,F63,F7,F82 python ...` | **passed** |
| `pip-audit --path .venv-test/lib/python3.12/site-packages --strict` | **passed** after updating stale test-env `certifi` |
| `check-jsonschema` on `docs/examples/*.json` | **2/2 valid** against CMP schemas |
| `maturin build --release` + clean-venv wheel install | **passed**; CLI help and control-plane/CDN smoke passed |
| `maturin sdist` + clean-venv source install | **passed** on macOS arm64; CLI help and bundled SDK asset smoke passed |
| `npm test` (`sdk/web`) | **11 passed** |
| `swift build` / `swift run PyTagManagerChecks` (`sdk/ios`) | **passed**, 19 checks |
| `swift test` (`sdk/ios`) | **blocked**: `no such module 'XCTest'` (Command Line Tools only) |
| Android build | **blocked**: no Android SDK/emulator configured |
| PyTagShield 0.2.0 Linux install probe | **failed**: only macOS arm64 wheel, no sdist |

The four skipped Python tests were environment-gated and skipped, not disabled
or weakened. No live PyTagShield HTTP deployment, PyCustomerHub stack, CDN
provider or external vendor account was available; none is claimed as tested.

## G. Security, privacy and tenant isolation

### Controls present in code

These are code/source observations; only behavior covered by the commands in
section F is claimed as tested.

- Event validation rejects unknown fields, oversized payloads, bad timestamps,
  malformed consent, invalid IDs and sensitive property names. Responses do not
  echo event properties.
- PyTagShield forwarding uses bounded timeouts, bounded response size, no
  redirects, no proxies from environment variables, optional bearer token via
  `env:`/`file:` reference, HTTPS by default and private/loopback rejection
  unless explicitly enabled.
- Collection has optional bearer auth, per-source token-bucket limiting,
  request-size boundaries, bounded batches, event-ID dedupe and sanitized
  forwarding outcomes.
- Control-plane secrets are references, not literals in exports; projected
  PyTagShield files are written with mode `0600`.
- PyTagShield remains independently responsible for consent resolution,
  minimization, pseudonymization and destination enforcement. PyTagManager does
  not claim compliance or delivery.
- Rust and Python dependency audits pass. The lockfile patch fixed three
  certificate-validation advisories; no API or direct dependency range changed.

### Security controls added 2026-10-22

- Batch rate limits now charge one token per event instead of one per request,
  removing the batch-amplification path.
- Client IP for rate limiting can use a forwarding header only when the direct
  peer is in an explicitly configured trusted-proxy CIDR. Untrusted peers,
  malformed headers and all-trusted chains fall back to the socket peer.
- Local HTTP tests cover spoof rejection, proxy-chain selection, malformed
  headers, per-event batch accounting and invalid proxy configuration. No live
  nginx/CDN deployment test was run.

### Open security issues

1. **Consent authority is unverified.** PyTagManager forwards the client consent
   map unchanged; it does not enforce consent. No live PyTagShield policy test
   was run. Do not describe the result as tamper-proof consent.
2. **No tenant isolation in the event contract or collector.** Tenants are not
   represented; the collector allowlists container IDs only. Do not deploy one
   endpoint for mutually untrusted tenants without an external isolation layer.
3. **Collection defaults are permissive.** CORS defaults to `*`, the API token
   is optional and the endpoint is unauthenticated unless configured. This may
   be intentional for public browser collection, but it is an abuse surface.
4. **`ThreadingHTTPServer` has unbounded worker threads.** The socket timeout and
   body limits reduce impact but do not cap concurrency.
5. **Exactly-once behavior is unverified.** Dedupe is SQLite-backed and
   completion is recorded after forwarding by code inspection. No crash/retry
   or multi-host test was run; a distributed idempotency guarantee is not
   claimed.
6. **Event-ID idempotency is unverified end-to-end.** Source inspection found
   PyTagShield generating its own event ID and no use of
   `x-pytagmanager-event-id`; no live idempotency test was run. Direct Shield
   ingestion bypasses collector dedupe.
7. **SSRF resistance is unverified.** The URL is checked at client construction
   and urllib resolves it later (code inspection). Redirects are disabled. No
   DNS-rebinding/TOCTOU test exists, so pinned-IP resistance is not claimed.
8. **Counterpart PyTagShield security is unverified.** Source inspection noted
   no visible outbound destination allowlist, optional ingest auth when no
   token is configured, and no auth middleware on some GET routes. No live
   PyTagShield security test was run. Treat these as source-review findings for
   that repository to confirm and fix.
9. **Subject IDs are only format-checked.** The schema says not to use email,
   phone or advertising IDs, but validation cannot prove that. Redaction and
   pseudonymization depend on upstream SDKs and PyTagShield policy.
10. **Control-plane authentication is not implemented.** Source inspection found
    no control-plane API or auth layer; no live control-plane test exists. Do
    not expose the provisional contract as if it were protected.

## G2. Cross-repo Squid blockers (reported 2026-10-23)

These are cross-repo blockers, not PyTagManager feature gaps. They are recorded
here so no adapter, schema or delivery claim is invented ahead of the contract.

| Integration | Status | Key gap | Next move owner |
|---|---|---|---|
| PyCustomerHub + Squid | **BLOCKED** | OCDS envelope vs Squid envelope v1; no schema registration; no write-key auth on the edge gateway | PyCustomerHub |
| PyReverseETL + Squid | **BLOCKED** | No `Idempotency-Key` header; no per-record Squid payload contract | PyReverseETL |
| PyTagShield + Squid | **UNVERIFIED/OPEN** | Consent attachment (records vs events vs both); PyTagShield server binary was a no-op in the audited tree | PyTagShield |
| ClusterAudienceKit / PyTagManager + Squid | **PARTIAL** | PyTagManager findings schema/write plan is defined; Squid acceptance and live write test pending. Segment schema remains ClusterAudienceKit | Squid + PyTagManager |

PyTagManager now owns one half of the findings contract: a versioned
`tagManagerFinding` object, record schema and lookup/upsert plan
(`docs/SQUID_FINDINGS.md`). That does not resolve the blocker until Squid accepts
the metadata contract and a live write test passes. PyTagManager does not add a
Squid runtime dependency or credential path.

## H. Remaining gaps, blockers and counterpart changes

### PyTagShield

- Add and document a real control-plane contract: registration/pairing, scoped
  auth, revision upload/fetch, activation/rollback, acknowledgement,
  effective-version lookup, reconciliation and audit.
- Provide an effective-config/delivery evidence API if server delivery claims
  are ever to be verified.
- Provide a runnable HTTP server bootstrap and a live integration test target.
- Add outbound destination URL validation/SSRF protection.
- Decide whether client event IDs can be used as idempotency keys.
- Document consent authority (client assertion vs stored/server decision).

### PyTagManager

- Keep live control-plane sync unimplemented until the counterpart contract is
  real; use a fake/test double only in contract tests.
- Run a live reverse-proxy/CDN test for the trusted-proxy rate-limit path
  (local HTTP tests exist; no live deployment was exercised).
- Validate per-event batch accounting under live traffic and tune limits
  against expected client behavior.
- Consider a bounded worker pool for the collection server.
- Add a shared/distributed idempotency strategy only if multi-host collection is
  actually required.
- Revisit anonymous identity semantics if a stable anonymous/session identifier
  becomes part of event v1.

### PyCustomerHub

- Agree on a mapping from PyTagManager event v1 to PyCustomerHub `EventEnvelope`:
  tenant source, schema name/version, identity namespaces, `source.type/name`,
  `data` vs `properties`, consent representation and event-ID reuse.
- Provide a non-production test stack or contract fixture if an adapter is to be
  declared verified.
- Do not add a PyCustomerHub dependency to core PyTagManager; make any adapter
  optional and explicitly labelled until verified.

### Other ecosystem repositories

- ClusterAudienceKit, PyReverseETL and Squid-CRM remain out of scope unless a
  concrete event/segment/activation contract is agreed. No speculative adapter
  should be added.
- QuillSift should not be added as a second crawler without a design decision
  that supersedes MudFish ownership.

## I. Compatibility requirements and recommended next steps

1. Preserve event schema v1, CLI names/options and existing exporter output.
2. Treat PyTagShield config projection and event forwarding as separate
   contracts; do not infer sync/activation from either.
3. Keep `pytagshield` optional. Native contract tests skip when it is absent.
   A macOS CI contract job installs `pytagshield==0.2.0` explicitly; its remote
   GitHub Actions execution has not yet been observed.
4. Implement a fake control-plane adapter only after the provisional envelope
   and state machine are agreed.
5. Before any PyCustomerHub adapter, write a mapping fixture and decide tenant,
   schema and identity semantics; otherwise leave it explicitly missing.
6. Run iOS XCTest and the Android build in CI or a full SDK environment before
   upgrading the internal SDK contract status from PARTIAL.
7. Do not claim live PyTagShield, PyCustomerHub, CDN or vendor-delivery
   compatibility from mocked tests.

### Known stubs and planned-but-unbuilt items

- `ClaudeIntentClassifier` raises `NotImplementedError`; only deterministic and
  local-Ollama classification exist.
- Playwright Test Candidate exports intentionally end in
  `NotImplementedError`/`test.fixme`; they are drafts, not runnable verified
  tests.
- PyTagShield live control-plane synchronization is blocked on the counterpart.
- PyTagShield 0.2.0 has no Linux wheel or sdist; Linux integration requires a
  source build from the PyTagShield checkout.
- PyCustomerHub ingestion adapter is missing/blocked on contract decisions.
- Squid findings contract is defined on the PyTagManager side but remains
  proposed; Squid metadata acceptance, API-key provisioning and live writes are
  pending.
- Multi-host dedupe and live trusted-proxy/reverse-proxy verification are not
  built; local trusted-proxy header tests exist.
- Broader deferred feature work (CMP depth, cloud intent classification,
  data-layer recommendations, XDM, enterprise audit, scale crawling, mobile
  discovery, cross-platform governance) is tracked in `QUEUE_STATUS.md` and
  `docs/ROADMAP.md`; it is not part of this integration baseline.
