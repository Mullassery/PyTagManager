# Bundle role — MarTech customer-data loop

This repository is part of the **MarTech customer-data loop** bundle. Portfolio-level rationale,
reuse map, and phases are in [`Mullassery/BUNDLES.md`](../Mullassery/blob/main/BUNDLES.md).

- **Role:** Measurement and runtime tracking QA
- **Upstream/downstream:** MudFish (crawl/fetch), PyCustomerHub (events), PyReverseETL (activation), StatGuardian (quality gate)
- **Current integration state:** MudFish tag-pinned dependency and event contract v1 are implemented; PyTagShield config/event adapters are implemented, live control-plane sync is blocked. See [`ECOSYSTEM_INTEGRATION.md`](../../ECOSYSTEM_INTEGRATION.md).
- **Next integration step:** PyTagShield control-plane contract, then a deliberate PyCustomerHub event-envelope mapping decision. Squid write paths are blocked until envelope/schema registration, edge write-key auth, idempotency and consent-attachment semantics are agreed. PyTagManager's findings half is now defined in `docs/SQUID_FINDINGS.md`; Squid acceptance and a live write test remain pending.
- **Non-goal:** Become a CDP or tag manager.

## Contract checklist

- [x] Versioned interface (package/crate/API), not an unpinned git URL — MudFish crates pin `rust-v0.1.3`.
- [x] Optional extra or separate service; standalone use remains possible — PyTagShield and MudFish are not browser/QA dependencies.
- [x] Shared event/profile/observation contract documented where relevant — `schemas/events/v1/`.
- [x] Integration test or demo proves the boundary — `tests/crawl_integration.rs`, `tests/python/test_ingest.py`, `tests/python/test_control_pytagshield.py`.
- [x] Competitive context recorded in `AUDIT_FINDINGS.md`.

See `COMPETITIVE_INTELLIGENCE.md` for the required check before roadmap or
feature work on this bundle.
