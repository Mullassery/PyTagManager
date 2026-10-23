# Queue status — 2026-10-22

This file records what was shipped, what is blocked/failed, and what is rejected for this repository. It complements `AUDIT_FINDINGS.md`.

## Shipped
- Lighthouse ingestion (`pytagmanager lighthouse`) with normalized scores/Core Web Vitals,
  plus repeated-run `lighthouse-ci` medians/ranges/budgets/failed-run retention.
- CMP-audit vertical slice (`pytagmanager cmp audit`): signature adapters, Cookiebot,
  Didomi and OneTrust state, Google Consent Mode, IAB TCF v2 and GPP metadata,
  data-only custom adapter files,
  pre/post-choice request ordering, reload persistence, stable findings, v1 JSON schema,
  and explicit authorization before any consent click.
- GTM usage index + drift blast radius; `gtm-plan` dry-run planner.
- `--fail-on-regression`, scheduled GitHub workflow, Click CI fix, docs aligned to 0.5.0.
- Collection abuse controls: batches consume one rate-limit token per event, and
  forwarding headers are trusted only from explicitly configured proxy CIDRs.
  Local HTTP tests cover spoof rejection, proxy chains, malformed headers and
  batch accounting.
- Squid findings contract v1 (`pytagmanager squid manifest|findings`): proposed
  `tagManagerFinding` object/field manifest, stable finding records, record schema
  and lookup/upsert plan. No live Squid write or metadata creation.
- SDR-driven validation v1 (`diagnose --sdr`): JSON/CSV SDR loading, event and
  parameter checks, alignment scoring, page/selector conditions, optional network
  observation and `--fail-on-sdr-mismatch` CI gate. No cross-platform network
  parameter equivalence or consent verdict is claimed.

## Criticality order (2026-10-22)

Priority is based on exploitable security impact, release/install integrity, then
product value. OWASP API4:2023 (Unrestricted Resource Consumption) and spoofable
forwarding headers make the collection endpoint the first blocker.

1. **P0 — Collection abuse controls.** Per-event batch accounting and opt-in
   trusted-proxy identity are now built and locally tested. Live nginx/CDN
   deployment remains unverified.
2. **P0 — Release integrity.** The published PyPI artifact is still macOS arm64
   only; multi-platform wheel/sdist coverage and clean-install verification are
   the next release blocker.
3. **P0 — Collection resilience.** Bounded worker concurrency, multi-host
   idempotency, and DNS-rebinding-resistant forwarding remain open.
4. **P1 — CMP depth.** Continue documented vendor readers, then multi-page/SPA
   consent journeys and consent-aware GTM configuration joining.
5. **P1 — Data-layer recommendations.** Parameter `available` flags,
   JSON-LD/microdata prefilling, implementation guide and golden tests.
6. **P1 — SDR depth.** Cross-platform network parameter contracts, SPA
   journeys, multi-page condition joins and SDR coverage reporting.
7. **P2 — Enterprise audit, scale crawl, cross-platform governance, XDM.**
8. **Blocked/deferred — Control-plane sync, PyCustomerHub adapter, mobile
   discovery.** Do not invent external contracts or unverified compatibility.

## Pending phases

Execution order is dependency-driven, not a schedule commitment. "Shipped"
means present and tested; phases below contain only work that is still open.

| Phase | Status | Pending tasks | Gate / exit |
|---|---|---|---|
| **CMP depth** (post-0.6.0) | Active | More documented vendor state readers; multi-page/SPA consent journeys; raw TCF/GPP decoding; consent-aware GTM tag-configuration joining | Each new reader has a fixture, no raw consent strings in reports, schema/docs updated |
| **1 — Visual grounding** | Partial | Computer-vision element understanding (hero/pricing/carousel) and visual discovery of recommendations not present in the DOM; keep screenshot capture evidence-only | Visual candidates outperform DOM-only discovery on a labeled fixture without inventing findings |
| **2 — Cloud intent classification** | Planned | Extract shared candidate discovery; implement optional `ClaudeIntentClassifier`; batch candidates per page; labeled precision/recall eval; token/cost budget; deterministic fallback | Beats the rule-based baseline on the labeled set with bounded cost and no hard failure |
| **3 — Data-layer recommendations** | Partial | Parameter recommendations with `available` flags; JSON-LD/microdata prefilling; Markdown implementation guide; golden tests. Multi-format exporters already shipped | One recommendation set exports consistently to GTM plus at least two platforms, with missing data explicit |
| **4 — XDM modeling** | Planned | Map canonical events/data-layer fields to XDM field groups; bundle representative AEP schemas; add XDM required-field gaps to the handoff report. Adobe Tags export already exists | Generated XDM validates against bundled representative schema rules |
| **5 — Enterprise audit engine** | Planned | Importers for GTM/Adobe Launch/Segment/Snowplow; match imported config to discoveries; classify missing/duplicate/broken-selector/dead/unfired; selector liveness; remediation report and CLI | Seeded GTM export with one of each gap type surfaces all gaps |
| **6 — Scale and incremental crawl** | Planned | Persisted/resumable frontier; multi-worker fetching; scripted login; faceted-nav/pagination guardrails; Playwright infinite scroll; crawl snapshot storage; 10k-page load fixture and scheduling recipe. Basic crawl diff already exists | 10k+ pages crawl and diff within a defined time/resource budget without manual intervention |
| **7 — Mobile discovery** | Planned | Android layout/Compose analyzer; iOS Storyboard/SwiftUI analyzer; emulator/simulator automation; platform/screen model; Kotlin/Swift wrapper generators; reference apps. Mobile SDKs and fixtures exist, discovery does not | End-to-end recommendation-to-wrapper on one reference app per platform |
| **8 — Cross-platform governance** | Planned | Canonical event registry; route all exporters through it; cross-platform consistency audit; web/mobile demo | One canonical event resolves through both export paths and drift is flagged |
| **9 — Emerging touchpoints** | Exploratory | Kiosk and desktop accessibility-tree spikes; IoT/automotive/AR-VR/wearables/voice remain unscoped until a concrete reference integration exists | A scoped spike with a real target, not speculative integration work |
| **Control-plane sync** | Partial | Freeze `pytagshield.control.v1`; registration/pairing; prepare→validate→submit→ack→activate→verify→rollback state machine; live capability probe; published-config browser verification; keep client/server evidence distinct | Fake-client tests pass and docs still mark live compatibility as unverified |
| **Release engineering** | Partial | Automated multi-platform wheel/release workflow; git tag and GitHub release; clean-install CI; security negative tests; docs re-verified against tested behavior | Install works outside macOS arm64 and no release step is manual-only |

Immediate next slice is release integrity (multi-platform wheel/sdist and
clean-install verification). CMP depth remains the active product phase.
Control-plane sync and release engineering are cross-cutting and should be
scheduled alongside the product phase they unblock, not after all phases.

## Blocked / failed
- PyTagShield control-plane registration/sync/activation: counterpart exposes no control API; see `ECOSYSTEM_INTEGRATION.md`.
- PyTagShield 0.2.0 packaging: only macOS arm64 wheel, no Linux wheel or sdist; Linux requires a source build.
- PyCustomerHub event ingestion adapter: blocked on tenant/schema/identity mapping decisions; no adapter is claimed.
- PyCustomerHub + Squid: blocked on OCDS-vs-Squid envelope v1, schema registration and edge write-key auth (owner: PyCustomerHub).
- PyReverseETL + Squid: blocked on missing `Idempotency-Key` and per-record payload contract (owner: PyReverseETL).
- PyTagShield + Squid: unverified/open on consent attachment (records vs events vs both); server binary was a no-op in the audited tree (owner: PyTagShield).
- ClusterAudienceKit / PyTagManager + Squid: PyTagManager findings schema/write plan defined; Squid acceptance and live write test pending. Segment schema remains ClusterAudienceKit (owners: Squid + PyTagManager / ClusterAudienceKit).
- GTM write/apply needs a resource mapper and live credentials; `gtm-plan` is the safe review path.
- Full Playwright CI rerun is pending after the Click fix.

## Rejected / deferred
- Visual/screenshot grounding, XDM modeling, and mobile platforms — not required for web QA.
- Remainder of the enterprise CMP/audit engine beyond the shipped vertical slice: more
  documented vendor state readers, multi-page/SPA consent journeys, raw TCF/GPP string
  decoding, and consent-aware tag-configuration joining.

## Integration defects fixed 2026-10-22
- A 202 PyTagShield-contract response with body `status: rejected` was reported as forwarded; response status is now authoritative and fail-closed (local HTTP test).
- Anonymous events without `subject.id` shared `_anonymous`; they now use event-scoped `anon:<event_id>` identities.
- Added optional real-PyTagShield pipeline tests and local HTTP contract tests. No live PyTagShield HTTP server was run. Unverified gaps remain listed in `ECOSYSTEM_INTEGRATION.md`.

## Policy

Any future feature or upgrade must check `AUDIT_FINDINGS.md` and this file before implementation. A blocked item is retried only when its external dependency is available; a rejected item needs new user evidence or a design change to reopen.
