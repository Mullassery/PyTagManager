# Competitive intelligence in roadmap and upgrade work

**Policy date:** 2026-10-19

Competitive findings are an input to product decisions, not a one-off report.
Every pending roadmap item, new feature, and routine dependency upgrade should
check the repository's [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) before work
starts, and record the decision in the PR or changelog.

## Required check before building

1. **Read `AUDIT_FINDINGS.md`.** Find the relevant competitor row and the
   ranked next actions. If the finding is stale, update it with a dated source.
2. **Name the competitor and the user problem.** A feature is not justified by
   "competitor has it". State the workflow it unlocks, who needs it, and how
   often. Mark unverified demand as a hypothesis.
3. **Prefer reuse over new code.** Check whether an existing Mullassery repo
   already provides the capability (see `BUNDLES.md` in the profile repo and
   the bundle role file in this repo, when present). Typical reuse:
   - crawling/fetching/robots/SSRF → **MudFish**
   - architecture maps / PR diffs → **CodeAtlas**
   - data-quality contracts / validation → **StatGuardian**
   - token counting / cost tables → **PyTokenCalc**
   - dependency graph / advisories / SBOM → **PyDeepMesh**
   - segmentation / CLV / churn → **ClusterAudienceKit**
   - activation / lineage / PII → **PyReverseETL**
   - fleet state sync → **SyncFleet** (only after conflict resolution)
4. **Choose one disposition:** build, integrate, defer, or reject. Write it
   down. A rejection with a reason is a successful outcome.
5. **For routine upgrades**, check whether the upgrade closes a known
   competitor gap or breaks a differentiated capability. Run the tests that
   cover the affected path; do not merge a green build that silently changes a
   user-visible contract.

## PR / changelog checklist

- [ ] Competitor and source URL/date recorded (or "no direct competitor").
- [ ] User impact and frequency stated; unverified demand labelled.
- [ ] Reuse check done against sibling repos/bundles.
- [ ] Failure mode and rollback considered (especially auth, PII, cost).
- [ ] Docs/roadmap status updated honestly.
- [ ] Tests or a manual verification command included.

## Review cadence

- Refresh the competitor row when a release changes the capability.
- Re-check the full `AUDIT_FINDINGS.md` at least quarterly and before a major
  release.
- If a finding is wrong or stale, correct it in the same PR that relies on it.

## Non-goals

- Copying features for parity.
- Adding a dependency just because a competitor uses it.
- Treating star counts or download counts as proof of user need.

## OSS gap analysis — 2026-10-24

Scope: Compared PyTagManager's implemented GTM inspection, real-browser diagnosis, SDR validation, dictionary, CMP and performance tooling against the two actively maintained OSS projects closest to its workflow. Google Tag Assistant / GTM Preview is the proprietary baseline named in the README; it is not OSS and is therefore not a table row. No actively maintained OSS project was found that performs root-cause tag diagnosis across the DOM → dataLayer → network chain.

### Comparable OSS projects
| Project | GitHub | License | Last activity | Why it is the comparison |
| --- | --- | --- | --- | --- |
| Matomo Tag Manager | https://github.com/matomo-org/tag-manager | GPL-3.0 | Pushed 2026-10-23; 2,530 commits | OSS tag manager with containers, versions, import/export, environments and a preview/debug mode — the nearest OSS alternative to the GTM workflow PyTagManager inspects |
| walkerOS | https://github.com/elbwalker/walkerOS | MIT | Pushed 2026-10-23; 4,238 commits | 2024-2026 tag/collection layer positioned explicitly against GTM, with config-as-code, schema validation, consent-native collection and warehouse destinations |

Google Tag Assistant remains the feature benchmark for "what fired", and ObservePoint (commercial) for scheduled site-wide scans and consent validation; neither is an OSS comparison. `sahava/gtm-datalayer-test` is the closest OSS predecessor for automated dataLayer assertions, but its last push was 2018, so it is not treated as a maintained alternative.

### Capability comparison
| Capability | Ours | Matomo TM | walkerOS | Gap |
| --- | --- | --- | --- | --- |
| GTM container inspection/import | Yes | Partial | No | Matomo manages its own containers, not GTM exports |
| Tag management / publishing | No | Yes | Yes | We deliberately do not manage tags |
| Tag/container versioning | Partial | Yes | Yes | Ours is config revisions, not a publish lifecycle |
| Real-browser runtime capture | Yes | Partial | Partial | Ours captures DOM/dataLayer/network per journey |
| Root-cause diagnosis with confidence | Yes | No | No | Ours only |
| SDR / schema validation | Yes | No | Yes | walkerOS validates at collection; ours post-observation |
| Site-wide crawl and template clustering | Yes | No | No | Ours only |
| Cross-page consistency checks | Yes | No | No | Ours only |
| Consent evidence (pre/post choice) | Yes | Partial | Yes | Ours is evidence-only, no legal verdict |
| Performance isolation experiments | Yes | No | No | Ours only |
| CI regression gate | Yes | No | Partial | Ours exits non-zero on SDR/regression failure |
| Exporter / destination breadth | Partial | Partial | Yes | 7 exporters; walkerOS has many destinations |
| Runnable generated tests | Partial | No | No | Candidates end in `NotImplementedError` |
| Install on Linux/Windows | Partial | Yes | Yes | PyPI wheel is macOS arm64 only |

"Partial" for Matomo runtime capture reflects its preview/debug mode, which shows what fired but does not correlate a missing tag back to a trigger/variable cause. walkerOS "Partial" runtime capture reflects its event validation/observability model rather than GTM-specific tag execution. Our "Partial" versioning reflects immutable config revisions, containers, environments and CDN publication in the control plane, but GTM publishing itself is still manual.

### Gaps that matter (ranked)
1. **No always-on scheduled monitoring** — `docs/ARCHITECTURE.md` says recurring invocation is left to the caller's cron/CI, and the audit's P1 is a scheduled regression Action plus alerting. Teams comparing against ObservePoint-class tools expect scans to run and alert without wiring their own scheduler. Hurts QA/release teams. Effort M.
2. **GTM writes stop at a reviewed draft** — `gtm import` creates a draft revision and never activates it; unsupported triggers/variables are warned rather than applied. Matomo TM and walkerOS both close the loop from config change to deployment. Users still finish the job by hand in GTM. Effort M.
3. **Packaging limits adoption** — README and `ROADMAP_HONEST.md` both state the PyPI wheel is macOS arm64 only; Linux/Windows install the sdist and need a Rust toolchain. The OSS comparators are PHP/TypeScript and install on any host. Effort S-M.
4. **SDR validation is narrower than the name suggests** — it checks observed dataLayer presence, fields, types, allow-lists and page/selector conditions, but not GA4/Adobe/Segment network parameter equivalence, server-side delivery or consent enforcement. walkerOS validates events at collection time, before they reach a destination. Effort M.
5. **Exporter and tag-template breadth is thin** — 7 exporters (GTM/GA4/Segment/Snowplow/Tealium/RudderStack/Adobe Tags) versus Matomo's tag catalogue and walkerOS's destination set. Agencies auditing mixed stacks will hit a missing platform quickly. Effort M.
6. **Generated test candidates are not runnable** — README says drafts end in `raise NotImplementedError`, so the "turn findings into regression tests" workflow still requires a human rewrite. This is a weaker version of an otherwise unique feature. Effort S.

### Where we are differentiated
- Evidence-graded root-cause findings (`Confirmed` / `Highly likely` / `Possible` / `Needs investigation`) across interaction → DOM → dataLayer → GTM → network; neither OSS comparator attempts this.
- Site-wide crawling with page-template clustering and cross-page consistency ("51 of 342 product pages never send `add_to_cart`") has no OSS equivalent in this set.
- `--fail-on-sdr-mismatch` / `--fail-on-regression` make tracking correctness a CI gate, not a dashboard.
- Controlled performance isolation (block one script plus downstream dependencies and re-measure) plus read-only CMP evidence is broader than either tag manager.
- Apache-2.0 avoids Matomo's GPL-3.0 copyleft for embedding; local-first processing and no telemetry are explicit.

### Disposition
- **Build:** a scheduled runner with alerting, a real GTM workspace/publish path with human approval, runnable test generation, and multi-platform wheels.
- **Integrate/reuse:** keep MudFish for crawl primitives and Playwright for browser evidence; export into Matomo/walkerOS formats rather than reimplementing their tag runtimes.
- **Defer/reject:** visual/screenshot grounding, XDM modelling, deep mobile/non-web support, and becoming a tag manager or CDP remain out of scope.

### Sources
- https://github.com/matomo-org/tag-manager (GPL-3.0, README features incl. preview/debug, pushed 2026-10-23, accessed 2026-10-24)
- https://github.com/elbwalker/walkerOS (MIT, README config-as-code/schema/consent, pushed 2026-10-23, accessed 2026-10-24)
- https://github.com/sahava/gtm-datalayer-test (MIT, last push 2018 — prior art only, accessed 2026-10-24)
- https://support.google.com/tagmanager/answer/15212503 (Tag Assistant baseline, accessed 2026-10-24)
- Repo files inspected: `README.md`, `COMPETITIVE_INTELLIGENCE.md`, `AUDIT_FINDINGS.md`, `docs/ARCHITECTURE.md`, `ROADMAP_HONEST.md`, `pyproject.toml`, `Cargo.toml`
