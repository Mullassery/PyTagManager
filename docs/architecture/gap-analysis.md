# PyTagManager — Gap Analysis

- **Status:** Phase 0.
- **Baseline:** `main` @ `92bc000`; 23 Rust + 419 Python tests passing,
  4 skipped.
- **Companion documents:** `current-state.md`, `feature-preservation-matrix.md`,
  `target-architecture.md`, `pytagshield-integration.md`,
  `../implementation-roadmap.md`.

This document identifies what is missing between the verified current product
and the requested tag-management platform. It intentionally does **not**
propose replacing working components.

---

## 1. Headline gaps

| # | Gap | Evidence in current code | Consequence | Priority |
|---|---|---|---|---|
| G1 | No tag-management domain model | No container/tag/trigger/variable/environment/revision/publication modules; `recommend/models.py` has only `TrackingRecommendation` | Cannot author, approve, version, or publish tracking configuration | **P0** |
| G2 | No persistent configuration store | Product is stateless; writes only user-requested JSON files; no lock/atomic-write/migration layer | No durable containers, revisions, audit, or multi-run identity | **P0** |
| G3 | No stable identity system | `TrackingEvent.id` = fresh `uuid4()`; snapshot identity = URL; recommendation identity = `event_name@selector` | Cannot correlate PyTagManager and PyTagShield objects across restarts/edits | **P0** |
| G4 | No user-specifiable container identity | No container concept at all | User requirement — use a GTM ID such as `GTM-XXXXXXX` as the PyTagManager container ID — cannot be met | **P0** |
| G5 | No configuration schema/version contract | Only `SNAPSHOT_FORMAT_VERSION = 1` and `exportFormatVersion = 2`; no envelope, checksum, compatibility metadata | No safe synchronization or migration | **P0** |
| G6 | No validation/publish/rollback workflow | `gtm-plan` is a read-only diff; exporters are artifacts; no environment or activation concept | Cannot publish deliberately or recover from a bad change | **P0** |
| G7 | No consent-aware execution engine | Diagnostics observe consent events and redact payloads; no managed tag execution, consent gating, or variable resolution | Cannot enforce consent for managed tags | **P0** |
| G8 | No PyTagShield control-plane integration | Adjacent PyTagShield has ingest only; no registration/config/activate/ack endpoints; no adapter exists in PyTagManager | No synchronization; any claimed compatibility would be unverified | **P0/P1** |
| G9 | No auth/tenancy/audit/secret store | No users, roles, orgs, audit records, secret references, or API auth | Not safe as a self-hostable multi-user control plane | **P0/P1** |
| G10 | No HTTP/control API or UI | CLI and Python imports only | Platform is not yet operable as a service; acceptable for first slice only if documented | **P1** |
| G11 | No managed runtime execution or preview trace | Existing traces are diagnostic observations of a *site's* behavior; no evaluation of *managed* configs | Cannot answer "what would this config do?" before publishing | **P0** |
| G12 | No import/export mapping for managed revisions | Exporters accept `TrackingRecommendation`, not managed tags; no explicit importer | Cannot round-trip or migrate managed configuration | **P1** |
| G13 | Security hardening incomplete for control plane | SSRF only on Rust crawl; Playwright arbitrary navigation; webhook POST to any URL; no destination allowlist; no auth | Unsafe server-side operation and credential handling | **P0** |
| G14 | Documentation and packaging drift | Test counts, taxonomy status, crawler ownership, and CI security claims are stale; macOS-arm64-only wheel | Misleading status and limited install coverage | **P1/P2** |
| G15 | PyTagShield itself is incomplete as a product | No README/public API doc, empty Python binding crate, empty server `main`, no config-sync endpoints | Cannot honestly claim live integration | **P0 (blocking for Phase 4)** |

---

## 2. Gap detail by area

### 2.1 Domain model and ownership

Current:

- `TrackingRecommendation` is a generated suggestion from DOM analysis.
- `TrackingJourney`/`Diagnosis` describe observed runtime behavior.
- `CrawlSnapshot` describes crawl state.
- None of these are editable or authoritative configuration.

Needed:

- `Organization`/tenant, `Workspace`, `Container`, `Environment`,
  `ConfigRevision`, `Tag`, `Trigger`, `Variable`, `Destination`,
  `Integration`, `SyncRecord`, `Publication`, `AuditEvent`.
- Clear ownership: PyTagManager authors configuration; PyTagShield applies
  server-side configuration. Discovery data is evidence, not authority.
- Explicit conversion from recommendation → **draft** tag, requiring review.

### 2.2 Container identity (including the GTM-ID requirement)

The user requires that **PyTagManager's container ID be user-specifiable**, so
that a Google Tag Manager public ID (for example `GTM-ABC1234`) can be used as
the PyTagManager container ID.

This is a design requirement, not a small field addition. It creates these
questions:

- **Uniqueness scope:** per organization, not globally, so two tenants may
  legitimately reference the same external GTM ID.
- **Immutability:** after creation the ID must not change. Display names may
  change; identity must not.
- **Comparison/normalization:** preserve the user's spelling for display but
  enforce case-insensitive uniqueness to prevent `gtm-abc` vs `GTM-ABC`
  collisions.
- **Semantics:** using a GTM ID here does **not** mean PyTagManager owns or
  can mutate that GTM container. GTM remains an external destination /
  correlation reference until an explicit API integration is configured.
- **Import/clone behavior:** importing or cloning must require a new,
  non-conflicting ID (or an explicit `--as` mapping). Silent reuse is
  forbidden.
- **Filesystem safety:** user-supplied IDs must never be used raw as paths.
  Derive a safe storage key (hash/slug) and keep the user ID in the document.

### 2.3 Persistence and concurrency

Current:

- No store, transaction, lock, or migration mechanism.
- History files are append-and-diff with no multi-writer safety.

Needed for the first release:

- Durable container/revision/environment/integration/audit records.
- Atomic writes and a lock/compare-and-swap strategy for revisions.
- Optimistic concurrency: a revision is based on `parent_config_version`; a
  conflicting concurrent edit is rejected, not silently overwritten.
- Migration/backup/recovery procedure.
- A decision on file-backed JSON vs. SQLite (see target architecture and
  approval list). No new database should be introduced without justification.

### 2.4 Schema versioning and checksums

Current:

- `SNAPSHOT_FORMAT_VERSION = 1` is the only explicit schema version in the
  product; export artifacts carry vendor-shaped version hints but no unified
  contract.

Needed:

- `schema_version` for the managed configuration contract.
- Immutable `config_version` plus monotonic `revision_number`.
- Canonical serialization and `sha256:` checksum.
- Explicit compatibility rules and a migration function per schema version.
- Strict rejection of unknown **major** versions; additive fields allowed only
  where documented.

### 2.5 Trigger, variable, and consent evaluation

Current:

- Diagnostics parse observed dataLayer/network events; they do not evaluate
  user-authored conditions.
- PyTagShield has a route matcher (wildcards `*`/`?` and property equality) and
  consent resolution, but PyTagManager does not expose an equivalent managed
  model.

Needed:

- Typed triggers: page view, custom event, click/link, form submit, route
  change, DOM condition, consent change, variable condition.
- Declarative condition AST; no arbitrary `eval`.
- Deterministic ordering, explicit precedence, missing-value semantics, type
  conversion rules, and error behavior.
- Variables: static, page metadata, DOM, dataLayer, event payload, consent,
  and safe computed values.
- Sensitive-field redaction before trace rendering, export, or transmission.
- Consent gating for managed tags and adapters; server-side enforcement stays
  independent in PyTagShield.

### 2.6 Adapters and execution boundaries

Current:

- Seven exporters implement `List[TrackingRecommendation] -> dict`.
- `tagexec/server_side.py` only *detects indicators* of server-side tagging.
- No adapter executes a tag in a browser or sends a server-side event.

Needed:

- A documented adapter interface with separate operations:
  `validate`, `preview/evaluate`, `export`, `browser execution` (when
  implemented), `server-side delivery` (via PyTagShield only), and
  `verification expectation`.
- Priority destinations: GA4, Segment, generic HTTP/webhook; preserve all
  existing exporters.
- Explicit labels so "generated config", "executed in browser", and
  "delivered server-side" are never presented as interchangeable.

### 2.7 Preview and debugging

Current:

- `InteractionTrace`, `Diagnosis`, and JSON reports describe observed site
  behavior.
- No way to feed a draft managed configuration an event and inspect the
  decision path.

Needed:

- Execution trace: incoming event, resolved variables, evaluated triggers,
  selected/blocked tags, consent decisions and reasons, adapter results,
  errors, timing.
- Redaction of credentials, personal data, and sensitive values.
- Clear separation between a **simulated** preview and a **real-browser**
  verification run.

### 2.8 Identity and synchronization

Current:

- No integration/container/config/destination identity.
- No idempotency, acknowledgement, reconciliation, or activation.
- PyTagShield's actual API has no config-sync control plane.

Needed:

- Persistent `integration_id` (UUID), user-specified `container_id`,
  immutable `config_version`, `schema_version`, `destination_id`.
- Registration/pairing with scoped credentials and secret isolation.
- Versioned envelope + checksum.
- Sync lifecycle with idempotency keys, bounded retries, timeouts, duplicate
  handling, lost-ack reconciliation, conflict detection, and rollback.
- Explicit authority split and "ack ≠ delivery" rule.
- Adapter interface + test double until the real contract exists.

### 2.9 Security, privacy, and operations

Current strengths:

- SSRF guard on Rust crawl.
- Redaction denylist and opt-in storage capture.
- Read-only GTM scope.
- Dependency audit jobs.

Missing:

- Control-plane authentication/authorization and scoped tokens.
- Tenant isolation at every repository boundary.
- Audit records for create/edit/validate/publish/rollback/sync.
- Secret storage/reference model; no credentials in exports or browser assets.
- Destination allowlists and SSRF protection for user-configured webhooks.
- Safe template execution, resource limits, input size limits, rate limits,
  timeouts.
- Safe logging (no credentials/sensitive payloads).
- Secure default configuration and deployment hardening guide.
- Explicit statement that browser consent does not replace server-side
  enforcement and that no legal compliance is implied.

### 2.10 CSRF/SSRF nuance in the existing product

- `SECURITY.md` correctly discloses that Playwright-driven commands navigate
  arbitrary URLs without the Rust SSRF guard.
- `--alert-webhook` POSTs to an arbitrary URL without an allowlist.
- PyTagShield's audited webhook destination stores an arbitrary `url` and
  builds a request with no visible private-network/allowlist guard.

These are existing risks to preserve-and-document, not silently "fix" in a
way that changes behavior. Any hardening must be additive and tested,
especially because tests use loopback mock servers.

### 2.11 Supported destinations and taxonomy

Current:

- Seven exporters, full current taxonomy mapping.
- GTM export is a minimal valid-shape container JSON, not a full GTM schema.

Needed:

- Managed destination adapters for GA4, Segment, generic webhook (priority).
- Explicit statement of what each adapter supports in browser, server, export,
  and verification modes.
- No claim of full GTM compatibility. The existing GTM export remains an
  import artifact; `gtm-plan` remains read-only.

### 2.12 Documentation, packaging, and release readiness

Current:

- Strong planning corpus, but status drift (test counts, taxonomy gap, CI
  security claims).
- macOS arm64 wheel only; Linux/Windows build from source.
- No publish/release workflow; manual build/upload.
- No Python coverage measurement.
- No Python formatter/lint gate beyond a narrow ruff selection.

Needed:

- Accurate README/quickstart/self-hosting/migration/security/privacy docs.
- Feature matrix by operating mode and dependency.
- Reproducible packaging and CI (including real browser tests).
- Migration/import/export guide and clean-environment verification.
- Contribution guide updates for the new control plane.
- Keep Apache-2.0.

---

## 3. Security and correctness risk register

| Risk | Trigger | Impact | Mitigation (proposed) |
|---|---|---|---|
| Identity drift | New revision/clone/import reuses or regenerates IDs | Orphaned integrations, wrong activation | Immutable IDs; explicit import/clone conflict rules; tests for restart/duplicate import |
| Concurrent edit loss | Two writers update one container | Silent overwrite | `parent_config_version` compare-and-swap; locking; conflict error |
| Accidental production publish | A test or script activates an environment | Live tracking change | Protected environments; explicit activation command; tests assert no auto-publish |
| Ack misinterpreted as delivery | Sync success shown as "event delivered" | False operational confidence | Separate `synchronized` and `delivery verified` states; UI/report wording |
| Unsafe outbound URL | User-configured webhook reaches loopback/private network | SSRF | Destination allowlist + resolution/redirect checks; tests use explicit test-only escape hatch |
| Secret leakage | Token embedded in container export/browser bundle/audit | Credential compromise | Secret references only; redaction; export denylist; tests scanning exports |
| Unsafe expression/template | User-authored computed variable executes arbitrary code | RCE in control plane | Declarative AST + allowlisted operators; no `eval`; resource limits |
| Tenant leak | Repository query omits org scope | Cross-tenant data exposure | Org-scoped repository API and negative tests |
| Schema incompatibility | Receiver sees an unknown feature/version | Corrupt or rejected config | `schema_version` + capability negotiation; fail closed; migration tests |
| Mock presented as real compatibility | Fake PyTagShield adapter passes tests | False claim of integration | Mark adapter `UNVERIFIED`; separate contract tests vs. live tests; docs status |
| Documentation overclaim | New feature shipped partially | User trust loss | Status matrix updated per phase; "unverified" labels |

---

## 4. PyTagShield gap summary

Audited adjacent workspace: `../PyTagShield` (version `0.1.0`). It is not a
git checkout in this environment and has no README/public API document.

**Exists (observed in code):**

- Strict YAML `Config` (`server`, `ingest`, `consent`, `minimization`,
  `transforms`, `destinations`, `routes`, `delivery`) in
  `crates/pytagshield-core/src/config.rs`.
- Ingest pipeline: validation, consent resolution/store, deterministic
  transforms, minimization, routing, bounded delivery workers.
- HTTP routes in `crates/pytagshield-server/src/app.rs`:
  `POST /api/v1/event`, `POST /api/v1/batch`,
  `POST /api/v1/consent`, `GET /api/v1/consent/{distinct_id}`,
  `GET /api/v1/deliveries`, `GET /healthz`, `GET /metrics`.
- Optional bearer-token / `x-api-key` auth on ingest and consent writes when
  `ingest.token` is configured.
- Webhook envelope `pytagshield.event.v1`; PostHog and webhook destinations.
- Many unit tests inside the Rust crates.

**Does not exist:**

- Registration/pairing of a PyTagManager instance.
- Config upload/fetch/version/activation/rollback endpoints.
- A configuration envelope with `integration_id`, `container_id`,
  `config_version`, `schema_version`, checksum, compatibility metadata.
- Idempotency keys, acknowledgements, reconciliation, or audit of config.
- A working Python binding (`crates/pytagshield-python/src/lib.rs` is empty).
- A server entry point (`crates/pytagshield-server/src/main.rs` is `fn main()
  {}`).
- README/API/schema documentation.

**Conclusion:** live config synchronization is **not implementable against a
real contract today**. Phase 4 must build against a clearly marked
provisional contract plus a test double, unless PyTagShield gains the control
plane first. See `pytagshield-integration.md`.

---

## 5. Prioritized gap closure

| Order | Work | Why first |
|---|---|---|
| 1 | Foundation: IDs, schema, storage, validation, checksums, service API, regression harness | Every later feature depends on stable identity and safe persistence |
| 2 | Managed tag/trigger/variable/destination model + evaluation/preview | Delivers the core authoring workflow without touching live sites |
| 3 | Revisions, environments, publish, rollback, audit | Makes changes deliberate and recoverable |
| 4 | PyTagShield adapter + provisional contract + registration/sync states | Enables the integration story without inventing a false one |
| 5 | Published-config browser verification and server-side verification where real contract permits | Proves the published config actually works |
| 6 | Security negative tests, docs, packaging, CI, release hardening | Required for a credible first integrated release |

---

## 6. Explicit non-goals for the first integrated release

- Business analytics/reporting dashboards.
- Campaign/attribution reporting or a reporting database.
- Automatic mutation of live websites or GTM accounts.
- Automatic conversion of all discovered tags into executable managed tags.
- Claiming full GTM schema compatibility.
- Claiming PyTagShield live compatibility before its control contract exists.
- Mobile/kiosk/desktop discovery engines.
- Enterprise RBAC complexity before core workflows work.
