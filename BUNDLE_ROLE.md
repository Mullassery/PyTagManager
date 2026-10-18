# Bundle role — MarTech customer-data loop

This repository is part of the **MarTech customer-data loop** bundle. Portfolio-level rationale,
reuse map, and phases are in [`Mullassery/BUNDLES.md`](https://github.com/Mullassery/Mullassery/blob/main/BUNDLES.md).

- **Role:** Measurement and runtime tracking QA
- **Upstream/downstream:** MudFish (crawl/fetch), MessageBirds (events), PyReverseETL (activation), StatGuardian (quality gate)
- **Next integration step:** Emit a stable tracking-plan/event contract and consume MudFish as a versioned dependency.
- **Non-goal:** Become a CDP or tag manager.

## Contract checklist

- [ ] Versioned interface (package/crate/API), not an unpinned git URL.
- [ ] Optional extra or separate service; standalone use remains possible.
- [ ] Shared event/profile/observation contract documented where relevant.
- [ ] Integration test or demo proves the boundary.
- [ ] Competitive context recorded in `AUDIT_FINDINGS.md`.

See `COMPETITIVE_INTELLIGENCE.md` for the required check before roadmap or
feature work on this bundle.
