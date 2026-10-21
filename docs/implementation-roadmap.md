# PyTagManager — Implementation Roadmap

- **Status:** Historical implementation roadmap. Phases 1–3 and the GTM,
  public-context, CDN and collection extensions are implemented; use
  `docs/GETTING_STARTED.md`, `docs/ARCHITECTURE.md` and
  `docs/architecture/multiplatform-extension.md` for current status.
- **Baseline:** `main` @ `92bc000`; original audit baseline was 23 Rust + 419
  Python tests passing, 4 skipped. Current suites are run separately and
  reported in the extension/status docs.
- **Companion docs:** `docs/architecture/{current-state,
  feature-preservation-matrix,gap-analysis,target-architecture,
  pytagshield-integration}.md`.

This roadmap is sequenced so each phase is independently reviewable and
useful. Do not start a later phase before the prior phase's exit criteria and
regression gates pass.

---

## 1. Phase 0 — Audit (complete)

Delivered:

- `docs/architecture/current-state.md`
- `docs/architecture/feature-preservation-matrix.md`
- `docs/architecture/gap-analysis.md`
- `docs/architecture/target-architecture.md`
- `docs/architecture/pytagshield-integration.md`
- `docs/implementation-roadmap.md` (this document)

Verified baseline:

- 23 Rust tests pass; fmt/clippy clean.
- 419 Python tests pass; 4 Ollama-dependent tests skip.
- Real Chromium browser tests run (not mocked).
- No application code changed.

Exit gate: maintainers approve (or amend) the decisions in §5.

---

## 2. Prioritized plan at a glance

| Phase | Deliverable | Depends on | Size | Risk |
|---|---|---|---|---|
| 1 | Foundation: identity, schema, persistence, validation, service API, regression harness | Phase 0 approval | L | Medium |
| 2 | Managed tags/triggers/variables/destinations + evaluation/preview + draft conversion | Phase 1 | XL | High |
| 3 | Revisions, environments, publish, rollback, audit | Phases 1–2 | L | Medium |
| 4 | PyTagShield provisional contract + adapter + fake + registration/sync state machine | Phases 1–3 | L | High (contract not real) |
| 5 | Published-config browser verification + server-side verification where real contract permits | Phases 2–4 | L | High |
| 6 | Security negative tests, docs, packaging, CI, clean-install release readiness | All prior | M | Medium |

---

## 3. Phase 1 — Foundation and contracts

**Goal:** Establish durable identity, schema, storage, and service boundaries
without changing existing workflows.

### Work items

1. **Package skeleton**
   - New additive package: `python/pytagmanager/control/`
   - Modules: `ids.py`, `models.py`, `schema.py`, `conditions.py`,
     `store.py`, `service.py`, `checksums.py`, `errors.py`, `secrets.py`,
     `migrations.py`
   - No imports from PyTagShield; no new mandatory dependency unless approved.

2. **Identity**
   - UUID v4 generation and persistence for org/workspace/environment/
     revision/tag/trigger/variable/destination/integration/sync/audit.
   - User-specified `container_id` with validation, case-insensitive
     org-scoped uniqueness, immutability, and GTM-ID support.
   - Import/clone/duplicate rules.
   - Tests: persistence across restart, collision, clone/import conflicts,
     GTM-shaped IDs.

3. **Schema and checksums**
   - Initial `schema_version = "1.0"` with typed dataclasses and explicit
     validation.
   - Canonical JSON serialization + SHA-256 checksum.
   - Strict unknown-major handling; additive-field policy.
   - Tests: deterministic checksum, malformed/unknown fields, version
     migration stub.

4. **Persistence**
   - File-backed store layout under a configurable home.
   - Atomic write (`temp + fsync + replace`), per-container lock,
     compare-and-swap on `parent_config_version`.
   - Tests: atomicity, concurrent edit rejection, restart reload, corrupted
     document handling, backup/restore procedure.

5. **Secret references**
   - `env:` and `file:` references; permission checks; export/log redaction.
   - Tests: secrets never appear in serialized exports or audit; missing
     secret fails closed.

6. **Service API + additive CLI**
   - Typed service functions for create/list/inspect container, import/export,
     validate.
   - Additive CLI commands; existing commands unchanged.
   - Tests: CLI help, round-trip, exit codes, no regression in existing CLI.

7. **Regression harness**
   - Ensure full existing test suite remains green.
   - Add a CI job for control-plane tests.
   - No weakening of existing Rust fmt/clippy/pytest gates.

### Exit criteria

- Stable IDs survive restart and ordinary edits.
- `container_id` can be `GTM-XXXXXXX` and remains immutable.
- Duplicate import/clone fails safely or is explicitly idempotent.
- Checksums are deterministic and verified.
- Existing 419+4 Python and 23 Rust tests remain green.
- No existing CLI/export behavior changed.

---

## 4. Phase 2 — Tag management

**Goal:** Deliver the managed authoring model and a deterministic preview.

### Work items

1. **Domain model**
   - Tag, trigger, variable, destination models per target architecture.
   - Adapter registry additive to `export/base.py` (do not modify existing
     export dispatch behavior).

2. **Triggers**
   - Typed page_view, custom_event, click/link, form_submit, route_change,
     dom_condition, consent_change, variable_condition.
   - Declarative condition AST, deterministic ordering, documented
     missing-value/type rules, no `eval`.
   - Tests: every operator, precedence, malformed AST, depth/size limits.

3. **Variables**
   - Static, page metadata, DOM, dataLayer, event, consent, safe computed.
   - Precedence, null/missing handling, explicit conversions, errors.
   - Sensitive marking and redaction.
   - Tests: precedence, missing values, conversion errors, redaction.

4. **Consent-aware execution evaluation**
   - Required purpose per tag; blocked-with-reason output.
   - Tests: denied purpose blocks tag; no consent implies no managed
     execution; server-side enforcement documented as separate.

5. **Adapters**
   - GA4, Segment, generic HTTP/webhook first; preserve existing exporter
     formats.
   - Adapter validation and capability flags (`export`, `browser`, `server`).
   - Tests: adapter validation, legacy exporter outputs unchanged, no
     capability mislabeling.

6. **Draft conversion from discovery**
   - Explicit `recommendation → draft tag` with source evidence and warnings.
   - Never auto-approve or auto-publish.
   - Tests: discovered items remain drafts; approval required.

7. **Preview trace**
   - Incoming event → variables → triggers → selected/blocked tags → consent
     → adapter results → errors/timing.
   - Redacted, serializable, clearly labeled simulation.
   - Tests: trace shape, redaction, blocked reasons, malformed event.

### Exit criteria

- A user can create, inspect, validate, and preview a managed container.
- No live site or external account is modified.
- Existing crawl/recommend/export/diagnose tests remain green.
- Negative tests cover malformed configs and consent denial.

---

## 5. Phase 3 — Versioning and publishing

**Goal:** Make configuration changes immutable, reviewable, deployable, and
recoverable.

### Work items

1. **Revisions**
   - Immutable `config_version`, monotonic `revision_number`, parent link,
     checksum.
   - Diff between revisions (tags/triggers/variables/destinations).
   - Tests: immutability, diff correctness, checksum mismatch rejection.

2. **Environments**
   - development/staging/production/custom; protected flag.
   - No automatic production publish during tests/development.
   - Tests: environment isolation, protected environment authorization.

3. **Publish/activate/rollback**
   - Validate before activation; reject invalid replacement.
   - Point environment at an immutable revision; retain previous version.
   - Rollback to a known-good revision.
   - Tests: publish, rollback, invalid publish, no-overwrite guarantee.

4. **Concurrency and conflicts**
   - Optimistic concurrency on revision creation; explicit conflict errors.
   - Tests: concurrent edit, stale parent, retry semantics.

5. **Audit**
   - Append-only records for create/update/validate/publish/rollback.
   - Actor, timestamps, before/after checksums, result.
   - Tests: audit completeness, no secrets/sensitive payloads.

6. **Operational status**
   - Local state clearly distinguishes validated/published/active/failed.
   - Tests: status transitions, failure retention.

### Exit criteria

- Revisions are immutable and comparable.
- Publishing is explicit, authorized, and audited.
- Production cannot be published automatically by tests.
- Rollback works and is audited.
- Existing workflows unaffected.

---

## 6. Phase 4 — PyTagShield synchronization

**Goal:** Implement the integration against a **provisional** contract and
test double, without claiming live compatibility.

**Status update (2026-10-20):** static, fail-closed config projection to
PyTagShield `0.2.0` is implemented and verified with the Python binding
(`config pytagshield-export`). Control-plane registration/sync/activation
remains pending.

### Preconditions

- Phase 1–3 stable.
- Decision on whether PyTagShield will implement the proposed control-plane
  contract, or whether PyTagManager ships only the adapter/fake.

### Work items

1. **Contract documentation**
   - Freeze a provisional `pytagshield.control.v1` envelope and endpoint
     proposal in this repo.
   - Clearly label every endpoint/field as proposed/not implemented.

2. **Adapter interface + fake**
   - `PyTagShieldClient` protocol in PyTagManager.
   - In-process fake for shape/idempotency/state-machine tests.
   - No import of PyTagShield internals.

3. **Registration/pairing**
   - `integration_id` generation/persistence, pending/active/revoked states,
     secret references, audit.
   - Tests: duplicate registration, revocation, secret isolation.

4. **Envelope + sync lifecycle**
   - Prepare → validate → submit → ack → reconcile → activate → verify
     effective → rollback.
   - Idempotency keys, checksums, bounded retries/timeouts.
   - Tests: duplicate requests, lost ack, partial failure, incompatible
     schema, checksum mismatch, concurrent edits.

5. **Acknowledgement semantics**
   - Separate `synchronized` from delivery verification.
   - Tests assert an ack never yields a "delivered" claim.

6. **Live status**
   - A capability probe reports `unsupported`/`pending verification` when the
     real endpoints are absent.
   - No live test is claimed unless a real deployment and contract exist.

### Exit criteria

- Adapter/fake tests pass.
- State machine is deterministic and idempotent.
- Docs clearly mark live PyTagShield integration as pending.
- No existing workflow depends on PyTagShield.

---

## 7. Phase 5 — End-to-end verification

**Goal:** Verify published configurations using the existing real-browser
framework, and server-side behavior only where the real contract supports it.

### Work items

1. **Published-config browser verification**
   - Reuse `ObservationSession`/`agent.js`; do not replace diagnostics.
   - Verify selected tags/triggers/dataLayer/network effects for a published
     revision.
   - Produce a trace with real observations and a clear pass/fail/unknown
     status.
   - Tests: real Chromium, positive and negative fixtures, no mocks.

2. **Client/server boundary**
   - Label browser-observed evidence vs. server-reported evidence.
   - Never infer server-side delivery from a sync ack.
   - Tests: ensure UI/report wording matches evidence.

3. **Server-side verification (conditional)**
   - Only if PyTagShield exposes a real effective-config/delivery API.
   - Otherwise keep the capability marked unavailable and test the boundary.

4. **Performance/regression integration**
   - Reuse existing perf/site-wide history where relevant; do not build a
     reporting product.

### Exit criteria

- Real browser verification of a published config works.
- Client/server evidence is distinct and accurately labeled.
- No mock is presented as vendor/PyTagShield compatibility.
- Existing diagnostic behavior remains unchanged.

---

## 8. Phase 6 — Release readiness

**Goal:** Make the first integrated release safe, documented, and installable.

### Work items

1. **Security tests**
   - SSRF/destination allowlist (including redirects/DNS), secret redaction,
     authorization failures, tenant isolation, malformed/oversized input,
     rate/timeout bounds, unsafe template rejection.
   - Ensure test-only loopback escapes are explicit and not reachable in
     production paths.

2. **Documentation**
   - README/quickstart updates; current vs. target architecture diagrams.
   - Tag/trigger/variable reference; schema reference; adapter guide.
   - PyTagShield integration guide with provisional status.
   - Security and threat model; privacy/data-handling guide.
   - Installation/self-hosting, migration/import/export, troubleshooting.
   - Contribution guide and supported-feature matrix.
   - Explicit "works today / optional dependency / experimental / unverified"
     labels.

3. **Packaging and CI**
   - Reproducible build; multi-platform release plan (current wheel is macOS
     arm64 only).
   - Real-browser CI remains mandatory.
   - Add control-plane tests; keep audit jobs; do not weaken gates.
   - Clean-environment install verification.

4. **Migration/recovery**
   - Document schema migration, backup/restore, rollback, and disaster
     recovery.
   - Provide examples and import/export transformations.

5. **Release criteria**
   - No unverified claims in docs.
   - Reporting remains deferred.
   - Apache-2.0 preserved.

### Exit criteria

- Clean install works.
- Security negative tests pass.
- Docs match tested behavior.
- Existing capabilities and tests remain green.

---

## 9. Architectural decisions requiring approval

The following must be decided before Phase 1 implementation. Recommended
defaults are shown first.

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| D1 | **Container ID semantics** | User-specified, immutable, org-scoped, case-insensitive uniqueness; GTM IDs allowed; never a credential; never implies GTM ownership | Directly implements the user requirement without corrupting identity |
| D2 | **Persistence backend** | File-backed JSON with atomic writes + locking for the first release; revisit SQLite only for concurrent/server mode | Avoids unjustified DB/framework introduction; matches existing project style |
| D3 | **Control-plane surface** | Python service + additive CLI first; no HTTP server/web UI until the domain stabilizes | Keeps the first slice reviewable and avoids premature auth/UI complexity |
| D4 | **Schema versioning** | Semver `schema_version`; immutable config revisions; canonical JSON + SHA-256; unknown major fails closed | Required for safe sync and migrations |
| D5 | **Browser execution scope** | Phase 2 does validation/preview/export; Phase 5 adds real-browser verification. Do not claim production tag execution until a runtime bundle is designed and verified | Prevents overclaiming and accidental live changes |
| D6 | **PyTagShield contract** | Build adapter + fake against the provisional contract; mark live sync pending. Decide whether to modify the PyTagShield repo separately | The real control plane does not exist today |
| D7 | **Auth/tenancy model** | Org-scoped data model now; local filesystem permissions + scoped integration tokens first; minimal roles; no enterprise RBAC yet | Proportionate security without blocking core workflows |
| D8 | **Secrets** | `env:` / `file:` secret references; 0700/0600 permissions; no credentials in exports/browser/audit | Simple, auditable, no keychain dependency |
| D9 | **Destination scope** | GA4, Segment, generic HTTP/webhook first; other destinations only with implementation + tests | Matches existing exporter strengths and avoids false breadth |
| D10 | **Import/clone identity** | Require new ID or explicit `--as`; idempotent only for identical checksum; conflict otherwise | Prevents duplicate/ambiguous containers |
| D11 | **Reporting** | Keep deferred; expose operational/audit records with future-consumable interfaces | Avoids premature analytics stack |
| D12 | **Dependency policy** | No new mandatory runtime dependency for existing workflows; any new dependency requires an ADR and audit | Preserves install simplicity and existing value |

---

## 10. Definition of Done mapping

The first integrated release is ready when:

1. Existing PyTagManager workflows still function — **preservation matrix +
   every phase gate**.
2. Crawling, discovery, DOM analysis, export, and real-browser verification
   remain intact — **regression suites**.
3. Users can manage tags/triggers/variables and validated configs —
   **Phases 1–3**.
4. Stable integration/container IDs survive edits and restarts — **Phase 1**.
5. Revisions are versioned, comparable, and rollback-capable — **Phase 3**.
6. The sync contract is documented and testable — **Phase 4**.
7. PyTagShield is tested against its real contract when available; otherwise
   its incomplete status is documented — **Phase 4 + integration doc**.
8. Security/consent have meaningful negative tests — **Phases 2, 6**.
9. Installation works from a clean environment — **Phase 6**.
10. Documentation reflects tested capabilities — **Phase 6**.
11. Reporting remains deferred — **all phases**.

---

## 11. Immediate next step

Phase 0 is complete. Do **not** start Phase 1 code until the decisions in §9
are approved or amended. The first implementation PR should be narrow:

- control package skeleton,
- ID generation/validation (including GTM-shaped `container_id`),
- schema v1 models + checksum,
- file-backed store with atomic write/lock,
- tests for identity persistence and duplicate/clone handling,
- no changes to `src/`, existing exporters, existing CLI commands, or
  PyTagShield.
