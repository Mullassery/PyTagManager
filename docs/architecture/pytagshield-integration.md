# PyTagManager ↔ PyTagShield Integration Contract

- **Status:** Static configuration projection and event-data-plane mapping are
  implemented and verified against PyTagShield `0.2.0` (Python binding).
  **Live control-plane synchronization is still not implemented.**
- **Audit date:** 2026-10-22 (initial contract audit 2026-10-20)
- **PyTagShield workspace audited:** `../PyTagShield`, version `0.2.0`, git
  checkout `682f4ab`.
- **Evidence:** source inspection plus executed projection and pipeline tests.
  A generated document was loaded with `pytagshield.Config.from_yaml` and
  exercised through `pytagshield.Pipeline.process`, including allowed and
  denied consent. A mapped canonical event was also accepted and routed by the
  real `Pipeline.process` implementation. No PyTagShield HTTP server was
  started, no live endpoint was called, and the PyTagShield test suite was not
  run as part of this audit.

This document separates three things that must never be conflated:

1. **What PyTagShield actually exposes today** (observed from source).
2. **What PyTagManager proposes for a control-plane contract** (provisional,
   subject to agreement with PyTagShield).
3. **What remains unimplemented / unverified**.

---

## 1. Executive finding

PyTagShield exposes a working **event data plane** (ingest, consent, routing,
minimization, delivery) and a strict startup YAML configuration, but **no
configuration control plane** (registration, config upload/fetch, revisions,
activation, rollback, acknowledgements, reconciliation).

Consequences:

- PyTagManager can generate a PyTagShield-compatible runtime document from an
  immutable managed revision. This is implemented as a conservative,
  fail-closed projection.
- PyTagManager **cannot** honestly claim live PyTagShield synchronization
  today. There is no upload, activation, acknowledgement, or effective-version
  endpoint.
- The projection is not a 1:1 translation of every browser tag semantic. Only
  server-representable event-name routing is projected; everything else is
  reported.
- Source inspection found no registration, revision upload, activation,
  effective-version query, delivery reconciliation, or rollback endpoint. No
  live control-plane call was made.
- Client-provided consent is forwarded as input; the collector does not enforce
  consent. No live PyTagShield consent-policy test was run.
- The synchronization contract remains separate and provisional.

---

## 2. Observed PyTagShield data plane (real, from source)

### 2.1 HTTP routes

From `../PyTagShield/crates/pytagshield-server/src/app.rs`:

| Method | Path | Auth in observed code |
|---|---|---|
| `POST` | `/api/v1/event` | Bearer / `x-api-key` **only if** `ingest.token` is configured |
| `POST` | `/api/v1/batch` | Same |
| `POST` | `/api/v1/consent` | Same |
| `GET` | `/api/v1/consent/{distinct_id}` | **No auth middleware in the observed router** |
| `GET` | `/api/v1/deliveries` | **No auth middleware in the observed router** |
| `GET` | `/healthz` | Public |
| `GET` | `/metrics` | Public (Prometheus text) |

Auth details (`handlers.rs`):

- Accepts `Authorization: Bearer <token>` or `x-api-key: <token>`.
- If no token is configured, ingest/consent writes are unauthenticated.
- Uses a constant-time-ish comparison for the configured token.
- Body size and concurrency limits are configured in `ServerConfig`.

### 2.2 Ingest event shape

From `crates/pytagshield-core/src/event.rs`:

```json
{
  "event": "purchase",
  "distinct_id": "user-or-anonymous-id",
  "timestamp": 1720000000000,
  "properties": {"currency": "USD"},
  "consent": {"analytics": true}
}
```

- `event` is canonical; `name` is accepted as an alias.
- `distinct_id` required by default.
- Timestamp skew is bounded (default 12 hours).
- Property count/key length/event name length are bounded.
- Unknown top-level fields are effectively ignored by the parsed struct
  (the event parser reads known keys); configuration is strict
  (`deny_unknown_fields`) but event ingestion is not a full JSON Schema
  contract.

### 2.3 Response shape

`IngestOutcome` (`pipeline.rs`) includes:

- `event_id`, `event_name`, `status`
- effective consent map + `consent_source`
- `matched_routes`, `destinations`, `enqueued`, `rejected`, `skipped`
- transform/minimization reports

Statuses include `accepted`, `partially_accepted`, `backpressure`,
`rejected`. This is an **ingest result**, not proof that a downstream vendor
received the event.

### 2.4 Configuration model (static, at startup)

From `crates/pytagshield-core/src/config.rs`:

- Strict YAML `Config` with `deny_unknown_fields`.
- Sections: `server`, `ingest`, `consent`, `minimization`, `transforms`,
  `destinations`, `routes`, `delivery`.
- Consumed at process startup in `build_state()`; there is no observed
  runtime reload or versioned config endpoint.
- Routes match event names with `*`/`?` wildcards plus exact property values.
- Destinations: `posthog`, `ga4`, `meta`, `sgtm`, `webhook`, `log`.
- Consent: purposes (default `analytics`, `advertising`, `personalization`,
  `functional`), default policy `deny`, TTL'd bounded in-memory store.
- Minimization: PII drop list, allowlist, property cap, depth cap, string
  truncation, optional salted-hash pseudonymization, optional IP forwarding.
- Transforms: `rename`, `drop`, `set` (enrichment, consent-gated), `map`.

### 2.5 Delivery and security observations

- Delivery workers are bounded, retried, with deterministic backoff.
- Webhook envelope schema: `pytagshield.event.v1`
  (`crates/pytagshield-core/src/destination/webhook.rs`).
- `PosthogSettings`/`WebhookSettings` store destination hosts/URLs and
  headers directly in configuration.
- **No visible SSRF/private-network/allowlist guard** on webhook/PostHog
  outbound URLs in the audited code. This must be treated as an open security
  gap for a control-plane integration.
- The Python binding exposes `Config.from_yaml`, `Config.from_path`,
  `Pipeline.process`, consent helpers, and metrics.
- The server `main.rs` is still **`fn main() {}`** in the audited checkout; no
  binary bootstrap was observed. The library router and handlers exist.
- The Python binding README is present; there is no published control-plane
  API reference or config-sync schema.

### 2.6 Tests observed

Many `#[test]` functions exist across `pytagshield-core` (config, consent,
delivery, destinations, event, metrics, minimization, pipeline, route,
transform). The suite was **not executed** for this audit, and no server
integration tests were confirmed. Do not cite PyTagShield test results. The
separate projection check did execute the Python binding against a generated
document.

---

## 3. What is missing for synchronization

The following control-plane capabilities do **not** exist in the audited
PyTagShield snapshot:

| Capability | Status |
|---|---|
| Register a PyTagManager deployment / pairing | Missing |
| Issue scoped credentials for config sync | Missing |
| Upload a versioned configuration revision | Missing |
| Fetch current effective configuration | Missing |
| List revisions | Missing |
| Activate/deactivate a revision | Missing |
| Roll back to a previous revision | Missing |
| Acknowledge a revision with checksum/version | Missing |
| Idempotency/deduplication contract | Missing |
| Reconciliation after lost acknowledgement | Missing |
| Audit of config changes | Missing |
| Schema/version compatibility negotiation | Missing |

Therefore the contract in §4 is **provisional**. Static projection does not
change that: loading a generated document is not registration, upload,
activation, acknowledgement, or delivery proof.

---

## 4. Provisional control-plane contract (proposed, not implemented)

### 4.1 Versioning

- Contract name: `pytagshield.control.v1` (proposed).
- Transport: HTTPS JSON.
- All control requests authenticated with a scoped credential distinct from
  the public integration ID.
- Every request/response carries `schema_version`.
- Unknown major versions fail closed.

### 4.2 Registration and pairing (proposed)

A user registers a PyTagShield deployment with PyTagManager through an
authenticated, out-of-band-approved workflow:

1. PyTagManager creates a local `Integration` record with a generated
   `integration_id` (UUID) and a pending registration state.
2. The user supplies the deployment base URL and a scoped registration
   credential (or completes a one-time pairing challenge).
3. PyTagShield validates the credential and returns its supported contract
   versions and a deployment reference.
4. PyTagManager stores only non-secret metadata plus a `secret_ref`.
5. State transitions: `unregistered → pending → active` (or `error`/`revoked`).

Rules:

- `integration_id` is stable and never used as a credential.
- Credentials are never written to container exports, browser bundles, logs,
  or audit records.
- Registration is idempotent for the same `integration_id`.
- Revocation is explicit and audited.

Candidate endpoint shape (proposal only):

```
POST /api/v1/control/integrations
GET  /api/v1/control/integrations/{integration_id}
POST /api/v1/control/integrations/{integration_id}/revoke
```

### 4.3 Configuration envelope (proposed)

```json
{
  "integration_id": "3f1c...",
  "container_id": "GTM-ABC1234",
  "config_version": "9c2e...",
  "schema_version": "1.0",
  "revision_number": 7,
  "created_at": "2026-10-20T12:00:00Z",
  "payload": {
    "tags": [],
    "triggers": [],
    "variables": [],
    "destinations": []
  },
  "checksum": "sha256:<hex>",
  "compatibility": {
    "contract": "pytagshield.control.v1",
    "min_receiver": "0.1"
  },
  "idempotency_key": "sha256:<hex>"
}
```

- `payload` is the immutable revision content.
- `checksum` covers `container_id + config_version + schema_version + payload`
  using canonical JSON.
- `idempotency_key` is stable for `(integration_id, config_version)`.
- The envelope may carry non-secret metadata, never credentials.

Candidate endpoints (proposal only):

```
PUT  /api/v1/control/integrations/{integration_id}/revisions/{config_version}
GET  /api/v1/control/integrations/{integration_id}/revisions/{config_version}
POST /api/v1/control/integrations/{integration_id}/activate
GET  /api/v1/control/integrations/{integration_id}/effective
GET  /api/v1/control/integrations/{integration_id}/sync/{idempotency_key}
```

**These paths are invented for planning.** They must be reconciled with the
real PyTagShield implementation before any client code is declared compatible.

### 4.4 Lifecycle and state model

PyTagManager-side states:

```
draft → validated → pending_sync → synchronized → active
                         ↘ failed ↗
active → rolled_back
```

Definitions:

- **draft:** editable, not validated.
- **validated:** local schema/consistency checks passed.
- **pending_sync:** submitted; awaiting receiver acknowledgement.
- **synchronized:** receiver acknowledged the exact `config_version` +
  checksum.
- **active:** receiver reports this revision as effective for the intended
  environment.
- **failed:** validation, transport, or receiver policy failure; explicit
  error retained.
- **rolled_back:** a previously accepted revision is active again.

A receiver acknowledgement **must not** be interpreted as proof that a
downstream event was delivered. Delivery evidence is a separate status,
obtained from the receiver's own delivery records, and only when the real
contract exposes it.

### 4.5 Idempotency, retries, and reconciliation

- Use `(integration_id, config_version)` (or the checksum) as the idempotency
  key.
- Duplicate submissions of the same key/checksum return the same result
  without side effects.
- Bounded retries (count, exponential backoff, cap) and explicit HTTP
  timeouts.
- After a lost acknowledgement, reconcile by querying the revision/effective
  status, not by blindly re-posting a different payload.
- A payload with the same `config_version` but a different checksum is a hard
  integrity error.
- Concurrent edits produce a new revision; never overwrite an immutable one.
- Incompatible schema versions fail closed with a machine-readable error.

### 4.6 Activation and authority

Proposed authority split:

| Concern | Authoritative system |
|---|---|
| Authoring/validating a configuration revision | PyTagManager |
| Immutable revision identity and checksum | PyTagManager (verified by receiver) |
| Whether a revision is applied/effective server-side | PyTagShield |
| Server-side consent, minimization, routing, delivery | PyTagShield |
| Browser-side observation/verification evidence | PyTagManager |
| Production activation decision | Explicit human/authorized API action; neither system auto-publishes |

PyTagManager may request activation; it may not assume success until
PyTagShield reports the effective version. PyTagShield must remain
independently usable without PyTagManager.

---

## 5. PyTagManager-side integration

### 5.1 Implemented: static projection

Implemented in `python/pytagmanager/control/pytagshield.py` and exposed as:

```bash
pytagmanager config pytagshield-export CONTAINER_ID \
  --pseudonymize-salt "$PYTAGSHIELD_PSEUDONYMIZE_SALT" \
  --output pytagshield.yaml
```

Behavior:

- Loads one immutable config revision (latest by default, or
  `--config-version`).
- Projects only server-representable routing:
  - triggers become PyTagShield `match.events` patterns when they constrain
    `event.name` with `equals`, `in`, or `matches_glob`;
  - `page_view` triggers without a name condition become `page_view`;
  - `all` conditions are intersected and `any` conditions are unioned;
  - anything else (for example `data_layer` predicates, `not`, `exists`, or
    browser-only trigger types without an event name) is an explicit error.
- Projects destinations:
  - `ga4`, `posthog`, `meta`, `sgtm`, `webhook`/`http_webhook` (POST only),
    `log`, and `debug`;
  - unsupported kinds such as `segment` are explicit errors;
  - purpose-specific aliases allow one managed destination to serve tags with
    different consent purposes without weakening destination-level consent.
- Resolves credentials only through an explicit callback. The CLI resolves
  `env:`/`file:` secret references using the existing secret resolver. Missing
  credentials fail closed; there is no placeholder-secret path.
- Emits deterministic JSON, which is valid YAML and is accepted by
  `pytagshield.Config.from_yaml`.
- Writes output files with mode `0600` because the projected document embeds
  resolved credentials.
- Optionally validates the generated document with the installed
  `pytagshield` package (`--validate`, on by default). If the package is not
  installed, native validation is reported as skipped rather than passed.

Explicit non-goals:

- Tag parameters, variables, and browser-side trigger semantics are **not**
  applied. They are reported as warnings because PyTagShield routes the
  incoming event as-is.
- The projection does not upload, activate, or prove delivery.
- It does not replace PyTagShield's own consent/minimization enforcement.

Verified by `tests/python/test_control_pytagshield.py`; the generated document
was also loaded and exercised with PyTagShield `0.2.0`.

### 5.2 Implemented: event data-plane forwarding

`python/pytagmanager/ingest/pytagshield.py` maps the canonical event to the
documented `POST /api/v1/event` shape and sends only a bounded response summary
back to the collector:

- `event` / `name` -> `event`
- `subject.id` -> `distinct_id`, or `anon:<event_id>` when no subject was
  supplied (never a shared global `_anonymous` identity)
- RFC 3339 timestamp -> Unix milliseconds
- `properties` -> `properties`
- `consent.purposes` -> `consent`
- event id, correlation id and session id -> PytagManager diagnostic headers

Response status handling is fail-closed: `accepted` and `partially_accepted`
count as forwarded, `rejected` does not, `backpressure` is transient, and an
unknown/missing status is rejected instead of being reported as success. HTTP
202 alone is not treated as delivery proof. A local HTTP contract test covers a
202 response with a `rejected` body; no live PyTagShield server was run.

The adapter does not follow redirects, validates HTTPS/host resolution at
construction, rejects embedded credentials, bounds timeout and response size,
and supports an optional `env:`/`file:` bearer-token reference. A loopback HTTP
test server exercises the wire payload and response parsing; a live PyTagShield
HTTP deployment remains unverified.

### 5.3 Future control-plane client (proposed)

```python
class PyTagShieldClient(Protocol):
    contract_version: str

    def register(self, request: RegistrationRequest) -> RegistrationResult: ...
    def submit_revision(self, envelope: ConfigEnvelope) -> SyncResult: ...
    def get_sync_status(self, integration_id: str, idempotency_key: str) -> SyncResult: ...
    def get_effective(self, integration_id: str) -> EffectiveConfig: ...
    def activate(self, integration_id: str, config_version: str) -> ActivationResult: ...
    def rollback(self, integration_id: str, config_version: str) -> ActivationResult: ...
    def get_deliveries(self, integration_id: str, limit: int) -> DeliverySummary: ...
```

Requirements:

- Implemented in PyTagManager as an **adapter**, not by importing PyTagShield
  Rust internals.
- No dependency on PyTagShield for crawl/discovery/export/browser
  verification.
- A fake/test-double implementation for unit tests, clearly named and
  documented as a test double.
- An optional live implementation that is disabled/clearly labeled until the
  real contract is confirmed.
- Capability detection: if the receiver lacks an endpoint, report
  `unsupported`, not a fabricated success.

### 5.4 Test double rules

- The fake may validate envelope shape, idempotency, checksum, and state
  transitions.
- The fake **must not** be used as evidence of vendor/PyTagShield
  compatibility.
- Contract tests must be separate from live integration tests.
- Live tests are opt-in and require a real deployment, credentials, and
  contract version.

---

## 6. Security requirements specific to integration

1. **Credential isolation:** store only `secret_ref`; never put tokens in
   container JSON, exports, browser assets, preview traces, or audit.
2. **Scoped auth:** a sync credential may manage configuration/activation for
   its integration only; it is not an admin credential.
3. **No public-ID auth:** `integration_id`, `container_id`, and
   `config_version` are identifiers, never secrets.
4. **TLS:** production integrations require HTTPS; allow explicit localhost
   development with a documented warning.
5. **SSRF/allowlist:** the receiver URL and any configured destination URL
   must be validated; block loopback/private/link-local/cloud-metadata in
   production, with a test-only escape hatch.
6. **Integrity:** verify checksum and `config_version` before activation;
   reject mismatches.
7. **Audit:** record registration, submit, ack, activation, rollback,
   revocation, and failures with actor and checksums.
8. **Server-side privacy:** PyTagShield must independently enforce consent
   and minimization. A browser-side consent check is not sufficient.
9. **Rate/timeout limits:** bounded retries, request size limits, timeouts,
   and concurrency limits.
10. **Safe errors:** do not echo tokens or full sensitive payloads in error
    messages or logs.

---

## 7. PyTagShield independence requirements

- PyTagShield must continue to start and enforce policy without PyTagManager.
- PyTagManager must continue to crawl, discover, export, and verify without
  PyTagShield.
- Integration uses documented HTTP/JSON contracts, not shared private code.
- Neither project may claim the other's capabilities.
- The integration is optional and must not become a required install for the
  existing workflows.

---

## 8. Open questions / blockers

1. Will PyTagShield add a control-plane API? If yes, which paths, auth model,
   and schema?
2. Is configuration intended to remain startup-only (static YAML), or will
   PyTagShield support runtime revisions and activation?
3. How will PyTagShield report the **effective** config version and delivery
   evidence?
4. What is the intended trust boundary between a browser consent signal and
   server-side enforcement?
5. How should PyTagShield's destination URLs be allowlisted/SSRF-protected?
6. ~~Should the PyTagManager container payload map 1:1 to PyTagShield's
   `routes`/`destinations`/`transforms` config?~~ **Answered for the current
   static projection:** PyTagManager remains the higher-level model and
   generates a conservative `routes`/`destinations` subset. Richer browser
   semantics remain unprojected.
7. Where will integration secrets be stored (env/file/OS keychain)?
8. What is the compatibility policy for `pytagshield.control.v1` and future
   schema majors?
9. How will Linux deployments install PyTagShield 0.2.0? PyPI currently
   publishes only a macOS arm64 wheel and no sdist, so Linux requires a source
   build until packaging is extended.

Until these are answered against a real implementation, Phase 4 must stop at:

- documented provisional contract,
- adapter interface,
- test double,
- state-machine tests,
- and an explicit **live integration pending** status.
