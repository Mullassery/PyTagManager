# Audit findings — 2026-10-26

This file records the current portfolio-audit findings for PyTagManager. It is
documentation only; no code or release artifacts were changed. The fuller
evidence report is kept in the portfolio workspace at
`.audit/reports/PyTagManager/audit.md`.

## What it is

A local-first tag-management and analytics-QA platform: a MudFish/Rust crawler,
GTM inspection/import/export, runtime tag diagnosis, SDR validation, data
dictionaries, performance isolation, CMP/consent auditing, a control plane, and
an optional event-ingest service.

## Verified strengths

- Explicit evidence model: severity + confidence; server-side tagging is only
  inferred, never claimed as confirmed.
- Real Rust crawler with async concurrency, SSRF guard, robots/sitemap, retries,
  and per-host circuit breaking.
- Control plane uses atomic writes, immutable revisions, CAS, audit events,
  file locks, and `0700` storage.
- Secret references (`env:` / `file:`) keep raw credentials out of stored
  config; file secrets reject symlinks and group/world-readable modes.
- Ingest enforces body/batch limits, content type, constant-time API-token
  comparison, trusted-proxy CIDRs, and retry-aware dedupe (memory or SQLite WAL).
- Performance and consent claims are scoped and honest.
- 87 test files: 23 Rust and 650 static Python test definitions.

## Verified gaps and user-facing risks

- **SSRF asymmetry:** `crawl` uses the Rust fetcher guard, but Playwright-backed
  commands (`diagnose`, `scan-tags`, `dictionary`, `perf`, etc.) navigate
  caller-supplied URLs without it. This is severe if wrapped as a service.
- **Ingest defaults are unsafe for network exposure:** auth is optional,
  CORS defaults to `*`, and rate limiting is per-process/in-memory.
- **Rate-limit key map clears at 10k entries**, which resets limits under
  high-cardinality traffic.
- **Ingest runs on `ThreadingHTTPServer`**, not a hardened production gateway.
- **File-store control plane is single-host;** no cross-host consistency or HA.
- **Test count drift:** README says 737 Python tests; static count is 650. The
  historical internal audit says 404 and must not be cited.
- **macOS arm64 wheel only;** Linux/Windows require a Rust build.
- Live reverse-proxy/CDN, multi-host idempotency, and bounded-worker behavior
  are documented as unverified.
- Squid integration is a contract/proposal, not a live write path.
- Mobile SDKs are lightly verified.
- Local build artifacts (`_core.abi3.so`, `__pycache__`) are present but
  gitignored, not tracked.

## Direct positioning

Against ObservePoint, GTM Tag Assistant, Adobe Experience Platform Debugger,
and Tealium. The differentiator is open-source, crawl-scale runtime tracking QA
with cited evidence and confidence levels.

## Ranked next actions

1. P0: apply the Rust SSRF policy to all Playwright navigations, or enforce
   loopback-only browser commands.
2. P0: require ingest auth for non-loopback binds and replace wildcard CORS with
   explicit origins.
3. P1: add shared rate limiting and a bounded-cardinality key policy.
4. P1: publish one verified Rust/Python test command and reconcile 737 vs 650.
5. P1: add multi-platform wheels or explicitly scope binary support to macOS
   arm64.
6. P1: add live proxy/CDN and multi-host dedupe tests.
7. P2: add ingest metrics/tracing and a production server recommendation.
8. P2: label Squid and mobile as experimental until live verification exists.

## Do not build

- A full visual/screenshot QA suite, XDM modeling, or broad mobile/non-web
  coverage. Stay focused on web tag/consent evidence.

## Evidence gaps / validation needed

- No precision/recall benchmark for recommendations.
- No user validation of diagnosis rules.
- No multi-host idempotency or live CDN test.
- No device-level mobile verification.

## Recommended disposition

Invest as a flagship analytics-QA tool. The control plane and evidence model are
strong; the blockers are browser SSRF parity and safe network defaults.
