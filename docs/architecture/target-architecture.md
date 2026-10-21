# PyTagManager — Target Architecture

- **Status:** Proposed target architecture for approval. No implementation
  has been started.
- **Constraint:** Additive to the verified `0.5.0` baseline. Preserve all
  capabilities in `feature-preservation-matrix.md`.
- **Technology policy:** Keep Rust + Python + Click + maturin. Do not add a
  new frontend framework, database, message broker, or mandatory service
  without an explicit, documented justification.

---

## 1. Design principles

1. **Discovery remains the differentiator.** Crawling, detection, DOM
   analysis, recommendations, and real-browser verification stay first-class.
2. **Managed configuration is a separate authority from observation.**
   Discovered tracking is evidence; managed tags are reviewed configuration.
3. **Stable identity before features.** Every durable object gets an identity
   that survives edits, restarts, exports, and sync.
4. **Immutable revisions, explicit publication.** Nothing reaches an
   environment without validation and an authorized activation step.
5. **Fail closed.** Unknown schema majors, denied consent, missing
   credentials, and ambiguous sync states block progression rather than
   guess.
6. **No arbitrary code execution.** Triggers/variables use a declarative
   condition AST with allowlisted operators, not `eval`.
7. **Real evidence over mocks.** Browser verification uses real Chromium.
   Mocked/fake receivers are labeled as such.
8. **Separate capability planes.** Export, browser execution, server-side
   delivery, and synchronization are distinct operations with distinct
   statuses and evidence.
9. **Proportionate tenancy.** Build org scoping into the model now; do not
   build a full enterprise RBAC product before the core authoring workflow
   works.
10. **Backward compatibility.** Existing CLI commands, Python exports,
    exporter outputs, snapshot v1, and the Rust crawler contract remain
    intact.

---

## 2. Target component map

```
                        ┌──────────────────────────────────────────┐
                        │          PyTagManager CLI / API          │
                        │  crawl · recommend · export · diagnose   │
                        │  container · revision · publish · sync   │
                        └───────────────┬──────────────────────────┘
                                        │
        ┌───────────────────────────────┼────────────────────────────────┐
        │                               │                                │
┌───────▼────────┐             ┌────────▼─────────┐             ┌────────▼────────┐
│ Discovery &    │             │ Managed Control  │             │ Verification &  │
│ Evidence       │             │ Plane (new)      │             │ Sync (new)      │
│ (existing)     │             │                  │             │                 │
│ crawler        │             │ containers       │             │ Playwright      │
│ DOM graph      │◄── drafts ──│ tags/triggers    │── published ─►│ verification    │
│ recommendations│             │ variables        │   revisions  │ PyTagShield     │
│ diagnostics    │             │ destinations     │             │ adapter         │
│ dictionary     │             │ revisions        │             │ sync lifecycle  │
│ perf/testintel │             │ environments     │             │                 │
└───────┬────────┘             │ audit            │             └────────┬────────┘
        │                      └────────┬─────────┘                      │
        │                               │                                │
        ▼                               ▼                                ▼
  Crawl snapshots              Durable local store              PyTagShield deployment
  JSON reports                 (JSON documents + locks)         (contract-dependent)
```

The existing modules remain where they are. The new control plane is a
**peer** that consumes their output, not a replacement.

---

## 3. Domain model

Names are proposed; field details will be fixed with typed dataclasses and a
schema reference document in Phase 1.

### 3.1 Tenancy and ownership

```
Organization (tenant)
  org_id: UUID (stable, generated once)
  name
  created_at
  schema_version
    └── Workspace
          workspace_id: UUID
          name
            └── Container
                  container_id: user-specified string (see §4)
                  name, description
                  site_urls[]
                  external_refs{}          # e.g. {"gtm": "GTM-ABC1234"}
                  created_at, created_by
                  status: active | archived
                    └── Environment
                          environment_id: UUID
                          name: development | staging | production | custom
                          protected: bool
                          current_config_version: UUID | null
```

A container is the logical unit of tracking configuration for a website or
application. Workspaces are optional grouping; a single-workspace deployment
must still be valid.

### 3.2 Configuration objects

```
ConfigRevision
  config_version: UUID (immutable identity)
  revision_number: integer (monotonic per container, for ordering)
  container_id
  schema_version: semver string (e.g. "1.0")
  parent_config_version: UUID | null
  status: draft | validated | pending_sync | synchronized | active | failed | rolled_back
  payload: { tags[], triggers[], variables[], destinations[] }
  checksum: "sha256:<hex>"
  created_at, created_by
  validation: { valid, errors[], warnings[] }
  notes

Tag
  tag_id: UUID
  name, description
  type: adapter key (e.g. "ga4_event", "segment_track", "http_webhook")
  parameters: typed map
  trigger_ids[]
  variable_ids[]
  consent_purpose: string | null
  destination_ids[]
  enabled: bool
  adapter_version
  compatibility: { min_schema, adapter_contract }

Trigger
  trigger_id: UUID
  name
  type: page_view | custom_event | click | link_click | form_submit |
        route_change | dom_condition | consent_change | variable_condition
  conditions: Condition AST
  priority: integer
  enabled

Variable
  variable_id: UUID
  name
  type: string | number | boolean | json | list | null
  source: static | page_url | page_path | page_title | referrer |
          dom | data_layer | event | consent | computed
  source_ref: selector/path/expression AST
  default: typed value | null
  sensitive: bool
  enabled

Destination
  destination_id: UUID
  name
  kind: ga4 | segment | http_webhook | pytagshield | ...
  config: non-secret settings
  secret_refs: { token: "env:..." | "file:..." }
  enabled
```

### 3.3 Synchronization and audit

```
Integration
  integration_id: UUID (stable)
  container_id
  deployment_ref: non-secret receiver reference
  contract_version: string
  registration_state: unregistered | pending | active | revoked | error
  secret_ref: secret reference only
  created_at, last_seen_at, metadata

SyncRecord
  sync_id: UUID
  integration_id
  config_version
  direction: push | pull
  idempotency_key
  request_checksum
  remote_config_version: string | null
  state: pending | acknowledged | synchronized | failed | reconciled
  attempts, last_error
  acknowledgement: opaque, non-secret payload
  created_at, updated_at

Publication
  environment_id
  config_version
  previous_config_version
  activated_by
  activated_at
  status: active | rolled_back | failed

AuditEvent
  audit_id
  timestamp
  actor
  action: create | update | validate | publish | rollback | register |
          sync | revoke | delete
  object_type, object_id
  before_checksum, after_checksum
  result
```

Audit records are append-only. They must never contain secrets or raw
sensitive payloads.

---

## 4. Container ID: user-specified identity (including GTM IDs)

This section directly addresses the requirement: **PyTagManager's container
ID must be something the user can specify, so a Google Tag Manager ID can be
used as the container ID.**

### 4.1 Decision

`container_id` is a **user-supplied, immutable identifier** assigned at
container creation. It is the primary logical identity of the container in
PyTagManager.

Examples:

- `GTM-ABC1234` — a GTM public container ID
- `acme-web-prod`
- `shop-eu`

The CLI must offer an explicit option, for example:

```bash
pytagmanager container create --id GTM-ABC1234 --name "Acme web" ...
```

### 4.2 Semantics

- The ID is **not** a credential and must never be used for authentication.
- Using a GTM ID as `container_id` does **not** imply PyTagManager owns,
  controls, or can mutate that GTM container. GTM stays an external system.
  Optional `external_refs` records the relationship explicitly:
  `{"gtm": "GTM-ABC1234"}`.
- If the user chooses a GTM-shaped ID, keep it exactly as entered for display.
  Do not silently rewrite its case.
- A container may exist without any external reference. A container may also
  have an external GTM reference different from its `container_id`.

### 4.3 Validation and uniqueness

Proposed rules (to be frozen in Phase 1):

- Length 1–128 characters.
- Allowed characters: ASCII letters, digits, `.`, `_`, `:`, `-`.
- Must start with an alphanumeric character.
- No whitespace, path separators, control characters, or `..`.
- Preserve the supplied spelling.
- Enforce **case-insensitive uniqueness within an organization** to avoid
  `gtm-abc1234` / `GTM-ABC1234` ambiguity.
- Optional convenience validation: if the ID matches `GTM-[A-Z0-9]+`, record
  `external_refs.gtm` automatically only when the user explicitly opts in;
  otherwise do not infer ownership.
- Never use the raw ID as a filesystem path component. Derive a storage key
  from `org_id` + a hash/slug of `container_id`.

### 4.4 Lifecycle rules

| Operation | Rule |
|---|---|
| Create | User supplies ID; reject duplicates (case-insensitive, same org) |
| Edit | Display name/description/metadata may change; `container_id` is immutable |
| Clone | Require a new ID, or an explicit `--as <new-id>` mapping; never reuse silently |
| Import | If ID exists and checksum/content matches, treat as idempotent no-op; if content differs, fail with a conflict requiring `--as` or `--force` approval |
| Export | Include `container_id`; never include secrets |
| Migrate/restart | Load the persisted ID; never regenerate from content |
| Delete | Archive by default; hard delete only with explicit authorization and audit |

Tests required: duplicate creation, case-insensitive collision, clone/import
conflicts, restart persistence, export round-trip, and GTM-shaped IDs.

---

## 5. Identity model summary

| Identifier | Format | Stability | Purpose |
|---|---|---|---|
| `org_id` | UUID v4 | Immutable | Tenant scope |
| `workspace_id` | UUID v4 | Immutable | Grouping |
| `container_id` | User string (may be `GTM-XXXXXXX`) | Immutable after create | Logical container identity |
| `environment_id` | UUID v4 | Immutable | Environment identity |
| `config_version` | UUID v4 | Immutable | One configuration revision |
| `revision_number` | Integer | Monotonic | Human ordering within container |
| `schema_version` | Semver string | Immutable per revision | Contract version |
| `tag_id`, `trigger_id`, `variable_id`, `destination_id` | UUID v4 | Immutable | Object identity within a revision |
| `integration_id` | UUID v4 | Immutable | Cross-project registration identity |
| `sync_id` | UUID v4 | Immutable | One sync attempt/record |
| `audit_id` | UUID v4 | Immutable | Audit record |

Rules:

- Identity is generated **once** and persisted.
- Never derive durable identity solely from mutable content.
- Object IDs are stable across edits; a changed tag produces a new
  `config_version`, not a new `tag_id` (unless the object is deleted/recreated).
- `config_version` changes whenever payload content changes.
- Public IDs are identifiers, never credentials.

---

## 6. Persistence strategy

### 6.1 Proposed first implementation: file-backed JSON

No database is introduced in Phase 1. The existing project already favors
plain JSON files and has no DB dependency. A file-backed store keeps packaging
and self-hosting simple and is proportionate to the first control-plane slice.

Proposed layout (root configurable via `--home` / `PYTAGMANAGER_HOME`):

```
<home>/
  schema_version.json
  orgs/<org_id>/
    org.json
    workspaces/<workspace_id>/workspace.json
    containers/<safe_key>/
      container.json
      revisions/<config_version>.json
      environments/<environment_id>.json
      publications.jsonl
    integrations/<integration_id>.json
    sync/<integration_id>/<sync_id>.json
    audit/<yyyy-mm>.jsonl
  secrets/            # mode 0700; files 0600; referenced by secret_ref
  locks/
```

Use a safe key for `container_id` (for example
`<sha256(container_id)[:16]>-<slug>`), because user IDs can contain characters
that are unsafe as path components.

### 6.2 Atomicity, locking, and concurrency

- Write to a temp file in the same directory, `fsync`, then `os.replace`.
- Use an exclusive lock per container for revision creation.
- Compare `parent_config_version` before committing a new revision; reject
  concurrent edits with a clear conflict error.
- Never overwrite an active revision. Publish by pointing an environment at a
  validated immutable revision.
- Append-only audit records are written with `O_APPEND` and one JSON object
  per line.

### 6.3 When SQLite may become justified

Only if the product needs multi-process/server-mode writers, indexed queries
over many revisions, or transactional publication across objects. That
decision requires a new ADR and a migration path from file-backed storage.
Do not add SQLite pre-emptively.

### 6.4 Migration, backup, recovery

- Every stored document carries `schema_version`.
- Migrations are explicit functions applied in order; unknown major versions
  fail closed.
- Backups are directory copies taken under lock.
- Recovery documentation must include how to restore a previous revision and
  how to re-point an environment.

---

## 7. Schema versioning and checksums

### 7.1 Managed configuration schema

- `schema_version` is a semver string, starting at `1.0`.
- Additive optional fields may be introduced within a major version.
- Unknown major versions are rejected before validation.
- Validation is strict about required fields and types; unknown fields are
  either rejected or explicitly preserved in a `x-` namespace (decision to
  freeze in Phase 1).

### 7.2 Canonical checksum

`checksum = "sha256:" + hex(sha256(canonical_json({container_id,
config_version, schema_version, payload})))`

Where `canonical_json`:

- UTF-8
- object keys sorted lexicographically
- no insignificant whitespace
- deterministic number/string serialization
- excludes the checksum field itself

Checksums are used for integrity, deduplication, idempotency, and audit
"before/after" hashes. They are not identities.

---

## 8. Trigger and variable evaluation semantics

### 8.1 Condition AST

Allowed condition nodes (declarative, no `eval`):

```json
{"op": "equals",       "path": "event.name", "value": "add_to_cart"}
{"op": "contains",     "path": "page.url",  "value": "/products/"}
{"op": "starts_with",  "path": "page.path", "value": "/checkout"}
{"op": "matches_glob", "path": "event.name", "value": "product_*"}
{"op": "exists",       "path": "data_layer.cart.id"}
{"op": "gt"/"gte"/"lt"/"lte", "path": "event.value", "value": 0}
{"op": "in",           "path": "consent.analytics", "value": [true]}
{"op": "all"|"any"|"not", "conditions": [...]}
```

Rules:

- Paths are restricted to defined namespaces (`event`, `page`, `dom`,
  `data_layer`, `consent`, `variables`).
- `matches_glob` uses the same `*`/`?` semantics as PyTagShield's route
  matcher, to ease server-side mapping.
- No regex by default (avoids ReDoS); a future regex operator requires length
  and complexity limits.
- Conditions have depth/node/size limits.
- Evaluation order is deterministic: triggers sorted by `priority`, then
  declaration index (or another documented tie-breaker).

### 8.2 Variable precedence

Documented and tested precedence:

1. Event payload (`event.*`)
2. Data layer (`data_layer.*`)
3. DOM-derived value
4. Page metadata
5. Static default

Missing values resolve to `null` with an explicit `missing` status in the
trace. Type conversion is explicit (for example `to_number`), never implicit
truthiness. Errors are captured per variable and do not abort unrelated
evaluation unless a tag requires that variable.

### 8.3 Consent

- Tags declare a required consent purpose.
- A tag executes only when consent allows that purpose; otherwise it is
  recorded as blocked with the exact reason.
- Consent precedence follows the existing PyTagShield model where applicable:
  event consent > stored consent > configured default (fail-closed by
  default).
- Browser-side consent is **not** proof of server-side compliance;
  PyTagShield independently enforces its own consent and minimization.
- Redaction runs before trace rendering, export, and any transmission.

---

## 9. API boundaries

### 9.1 Phase 1–3 surface

- A Python **service layer** (typed functions/classes) under a new
  `pytagmanager.control` package.
- Additive CLI commands that call the service layer.
- No HTTP server and no web UI in the first slice. This keeps the change
  reviewable and avoids introducing a framework before the domain is stable.

Proposed CLI shape (names to be approved):

```
pytagmanager container create --id GTM-ABC1234 --name "..."
pytagmanager container list
pytagmanager config import/export
pytagmanager revision create/validate/diff/show
pytagmanager environment create/list
pytagmanager publish --container ... --environment staging --version ...
pytagmanager rollback --container ... --environment production --to ...
pytagmanager integration register/list/sync/status
pytagmanager preview --container ... --event event.json
```

Existing commands remain unchanged.

### 9.2 Future HTTP API

If a self-hosted service surface is required, expose the same service layer
through a thin adapter. That is a separate decision requiring:
authentication, CSRF/rate limits, request size limits, TLS/deployment
guidance, and an ADR. A web UI is not required for the first integrated
release.

### 9.3 Capability boundaries (must be explicit in every API/report)

| Operation | What it proves |
|---|---|
| Validate | Schema/consistency checks passed locally |
| Preview/simulate | The evaluator selected these tags for this synthetic event |
| Export | An artifact was generated in a vendor's format |
| Browser verification | A real browser observed these effects for this revision |
| Server sync acknowledgement | The receiver accepted the revision |
| Delivery verification | A downstream destination actually received an event |

No layer may report a stronger claim than the evidence it has.

---

## 10. Adapter architecture

### 10.1 Preserve existing exporters

`export/base.py`'s `EXPORTERS` registry and all seven builders remain
unchanged. New adapters are additive.

### 10.2 Proposed adapter protocol

```python
class ManagedTagAdapter(Protocol):
    adapter_key: str
    supported_schema_versions: tuple[str, ...]
    execution_modes: frozenset[str]  # export | browser | server

    def validate(self, tag: Tag, context: ValidationContext) -> ValidationResult: ...
    def build_export(self, tag: Tag, revision: ConfigRevision) -> dict: ...
    def build_runtime_payload(self, tag: Tag, event: EvaluationEvent) -> dict | None: ...
    def build_server_request(self, tag: Tag, event: EvaluationEvent) -> dict | None: ...
    def verification_expectation(self, tag: Tag) -> VerificationExpectation: ...
```

Priority adapters:

1. **GA4** — export (existing) + server-side mapping where supported.
2. **Segment** — export (existing) + server-side mapping where supported.
3. **Generic HTTP/webhook** — server-side (via PyTagShield) and exportable
   description.
4. Additional destinations only when implementation and tests justify the
   claim.

Do not conflate:

- Building an export artifact
- Executing in a browser
- Sending server-side
- Verifying delivery

### 10.3 Draft generation from discovery

`recommend_for_graph()` output may be converted into **draft** tags through an
explicit transformation that records source evidence:

- source recommendation (event name, selector, confidence, rationale, page)
- conversion warnings (for example: selector may be brittle, destination
  parameters unknown)
- `status: draft`, never auto-published

No discovered tag is silently treated as approved.

---

## 11. Preview, debugging, and verification

### 11.1 Deterministic preview trace

Given a synthetic event and a revision, produce:

```
Incoming event
Resolved variables (redacted)
Evaluated triggers (matched/not matched + why)
Tags selected
Tags blocked (consent/condition/disabled + reason)
Adapter results (export payload / would-send summary)
Errors and timing
```

The trace is a **simulation**, clearly labeled. It does not claim execution.

### 11.2 Real-browser verification

Reuse `ObservationSession` / `agent.js` wherever possible. Verification of a
published revision must produce real observations (DOM/network/dataLayer) and
must distinguish:

- client-side evidence observed in the browser
- server-side evidence observed only through the receiver's status/delivery
  records
- unverified claims

A full browser runtime bundle/injection mechanism is a Phase 5 decision; it
must not change the existing diagnostic path or replace its tests.

---

## 12. Security model

### 12.1 Assets

- Integration credentials / API tokens
- Destination secrets (API keys, webhook tokens)
- Tenant configuration and audit records
- Personal data observed during crawling/verification
- Published configuration integrity

### 12.2 Controls

- **Secrets:** stored as references (`env:`, `file:`), never in config
  payloads, exports, browser assets, logs, or audit. Files 0600, directory
  0700. No public ID is ever a credential.
- **Auth:** first release uses local filesystem permissions plus scoped
  integration tokens. If an HTTP API is added, it requires authentication
  before exposure. Multi-user roles are deferred but data is org-scoped now.
- **Tenant isolation:** every repository operation requires `org_id`; negative
  tests prove cross-org access fails.
- **SSRF/destination allowlist:** user-configured outbound URLs are validated
  against an allowlist and private/link-local/metadata ranges. Tests use an
  explicit test-only escape hatch for loopback fixtures.
- **Consent:** managed tags declare purposes; denied purposes block execution.
  Server-side enforcement remains in PyTagShield.
- **Input validation:** strict types, size limits, schema validation, bounded
  condition depth, bounded variable resolution.
- **Execution safety:** no `eval`, no arbitrary template code, allowlisted
  operators, per-evaluation resource limits.
- **Audit:** append-only records for create/edit/validate/publish/rollback/
  registration/sync actions, with checksums and actor.
- **Logging:** structured, redacted; never log tokens, full payloads, or raw
  personal data.
- **Rate limits/timeouts:** bounded retries, HTTP timeouts, queue limits,
  request size limits.
- **Secure defaults:** no production auto-publish, no unauthenticated exposed
  service, fail-closed consent, no IP forwarding unless explicitly enabled.

### 12.3 Threat model summary

| Threat | Control |
|---|---|
| Stolen integration token | Scoped token, rotation, secret refs, audit |
| Malicious config causing SSRF | Destination allowlist + private-range blocking |
| Secret exfiltration via export/preview/log | Secret isolation + redaction + export scan tests |
| Cross-tenant access | Org-scoped repository + negative tests |
| Concurrent edits / lost update | Optimistic concurrency + lock |
| Unauthorized production publish | Explicit activation + protected environment + audit |
| Malicious condition expression | Declarative AST + limits, no `eval` |
| Forged/stale sync ack | Idempotency key + checksum + reconciliation, not delivery proof |
| Sensitive payload leakage in traces | Redaction before rendering/persistence |

Legal note: these are engineering controls, not a compliance certification.
Deployments remain responsible for their own legal and operational
requirements.

---

## 13. Backward compatibility plan

- No changes to `src/` crawler behavior or DOM schema in Phase 1.
- No changes to the seven exporter builders or `EXPORTERS` keys in Phase 1.
- No changes to `SNAPSHOT_FORMAT_VERSION = 1`.
- No renames/removals in `pytagmanager.__init__` or existing CLI commands.
- New control-plane package is additive and optional.
- New dependencies require justification and auditing; the core package must
  still work without PyTagShield or a server.
- PyTagShield remains optional; its absence cannot break crawl/recommend/
  export/verify.

---

## 14. Open architectural decisions

See `../implementation-roadmap.md` §5 for the approval list. The most
important open choices are:

1. File-backed store vs. SQLite for the first control plane.
2. Python service + CLI only vs. adding a local HTTP API in the first release.
3. Whether managed tags execute browser-side in this release or only
   validate/preview/export/verify.
4. Exact user-specified `container_id` validation/uniqueness rules.
5. Whether to modify PyTagShield to add a control-plane contract, or build
   PyTagManager against a provisional adapter and defer live integration.
6. Minimal auth/role model for the first self-hosted release.
7. Secret storage mechanism (`env:`/`file:` references vs. OS keychain).
