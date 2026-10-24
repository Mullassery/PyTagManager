# Security Policy

## Supported versions

PyTagManager does not yet have a formal release/support matrix — see
[`docs/internal/ROADMAP_HONEST.md`](docs/internal/ROADMAP_HONEST.md) for current PyPI release status.
In practice, only the latest release on PyPI and the `main` branch receive
security fixes; there is no backport policy for older versions.

## Reporting a vulnerability

This is a solo-maintained open-source project with no dedicated security
team and no SLA. Please do **not** open a public GitHub issue for a
security vulnerability.

Instead, report it privately via GitHub's
[private vulnerability reporting](https://github.com/Mullassery/PyTagManager/security/advisories/new)
feature on this repository, if enabled, or by opening a issue titled
"Security contact request" with no vulnerability details, so a private
channel can be arranged.

There is no guaranteed response time. This is disclosed honestly rather
than promising a turnaround (e.g. "48 hours") that can't actually be
committed to by a single unpaid maintainer.

## Scope and known risk areas

Be aware of the following when using PyTagManager. Unless an item explicitly
cites an executed test, these are code/source inspection findings, not live
exploit results or runtime guarantees:

- **`pytagmanager crawl`/`diagnose`/`dictionary`/`scan-tags`/`perf` fetch
  arbitrary URLs you provide**, including via a real headless browser
  (Playwright) for the `diagnostics` extra's commands. The Rust crawler
  (`src/crawler/fetcher.rs`) has an SSRF guard blocking loopback and
  cloud-metadata addresses (see `fetch_rejects_loopback_url`,
  `fetch_rejects_cloud_metadata_url` in that module's tests) — this guard
  applies to the Rust-side crawl only, not to Playwright-driven commands
  (`--render`, `diagnose`, `dictionary`, `scan-tags`, `perf`), which will
  navigate a real browser to whatever URL you pass. Do not point these
  commands at internal/private network addresses you don't control.
- **`--capture-storage-values`** (in `diagnose`/`dictionary`) captures raw
  cookie/localStorage/sessionStorage values, not just keys/types. Even
  with this flag on, sensitive-looking keys are redacted
  (`observability/events.py`'s `is_sensitive_key`) — but this is a
  key-name heuristic, not a guarantee. Values that don't match a
  recognizable sensitive key name are captured verbatim if this flag is
  set. Off by default.
- **`--gtm-credentials`/`--ga4-credentials`** accept paths to your own
  GCP service-account JSON files, used only to call the GTM/GA4 APIs
  locally; PyTagManager does not transmit these credentials anywhere
  else. Treat them like any other credential file (don't commit them,
  don't pass world-readable paths in shared environments).
- **`--alert-webhook`** POSTs a JSON payload (`{"text": "..."}`) to a
  URL you supply when a tracking-health regression is detected. No
  authentication is added to this request beyond what the URL itself
  encodes (e.g. a Slack incoming-webhook URL's own secret path segment).
- **`OllamaIntentClassifier`/`OllamaPageTypeClassifier`** talk to a local
  Ollama HTTP endpoint (default `http://localhost:11434`) with no
  authentication. If you run Ollama on a shared or non-loopback address,
  that's outside PyTagManager's control.
- **The optional collection HTTP service has an unverified multi-tenant
  boundary.** It supports optional bearer authentication, CORS `*` by default,
  per-event batch accounting, opt-in trusted-proxy client identity and SQLite
  dedupe. Local HTTP tests cover spoofed forwarding headers, malformed headers,
  proxy chains and batch token accounting; no live proxy/CDN, abuse, multi-host
  or tenant test was run. If enabled, put it behind a trusted gateway with its
  own authentication, request limits and per-client quotas. Configure
  `--trusted-proxy-cidr` only for proxies that overwrite or append the real-IP
  header.
- **Exactly-once forwarding is unverified.** Code inspection shows SQLite dedupe
  with completion recorded after forwarding. No crash/retry or multi-host test
  was run; distributed idempotency is not claimed.
- **PyTagShield forwarding and consent authority are unverified end-to-end.**
  Code inspection shows URL validation at client construction and a later urllib
  resolution; no DNS-rebinding/TOCTOU test was run. Private/loopback targets
  require an explicit opt-in. PyTagManager forwards the client consent map and
  does not enforce consent; no live PyTagShield policy test was run. Delivery is
  not proven.
- **Subject IDs are only format-checked.** Do not put email addresses, phone
  numbers or advertising IDs in `subject.id`; the schema documents this, but
  validation cannot prove it. A downstream collector must not assume
  PyTagManager redacted subject values.
- **The self-hosted control plane is a local file store.** Source inspection
  found no user-authentication or tenant-isolation layer; no multi-tenant
  security test was run. Secret values are references, and projected files are
  written with mode `0600`, but the state directory must be protected by
  filesystem permissions. Do not expose it as a shared multi-tenant API.
- **Counterpart PyTagShield security is unverified.** Source inspection of the
  audited 0.2.0 tree noted optional ingest auth when no token is configured, no
  auth middleware on some GET routes, and no visible outbound destination
  allowlist. No live PyTagShield security test was run. Treat these as
  source-review findings for that repository to confirm before public exposure.
- **Dependency-vulnerability scanning runs in CI** (`dependency-audit` job).
  As of 2026-10-22, `cargo audit` and `pip-audit --strict` pass after updating
  three RustSec certificate advisories in `Cargo.lock`. No audit is a proof of
  absence; review advisories before each release.
