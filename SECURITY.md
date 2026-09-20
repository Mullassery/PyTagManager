# Security Policy

## Supported versions

PyTagManager does not yet have a formal release/support matrix — see
[`ROADMAP_HONEST.md`](ROADMAP_HONEST.md) for current PyPI release status.
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

Be aware of the following when using PyTagManager, disclosed here rather
than left implicit:

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
- Dependency-vulnerability scanning is not currently run in CI — see
  `ROADMAP_HONEST.md` and the note in `.github/workflows/ci.yml` about
  planned/unverified audit tooling.
