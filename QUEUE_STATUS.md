# Queue status — 2026-10-22

This file records what was shipped, what is blocked/failed, and what is rejected for this repository. It complements `AUDIT_FINDINGS.md`.

## Shipped
- Lighthouse ingestion (`pytagmanager lighthouse`) with normalized scores/Core Web Vitals,
  plus repeated-run `lighthouse-ci` medians/ranges/budgets/failed-run retention.
- First CMP-audit vertical slice (`pytagmanager cmp audit`): signature adapters, Cookiebot
  and Google Consent Mode state, pre/post-choice request ordering, reload persistence,
  stable findings, v1 JSON schema, and explicit authorization before any consent click.
- GTM usage index + drift blast radius; `gtm-plan` dry-run planner.
- `--fail-on-regression`, scheduled GitHub workflow, Click CI fix, docs aligned to 0.5.0.

## Blocked / failed
- GTM write/apply needs a resource mapper and live credentials; `gtm-plan` is the safe review path.
- Full Playwright CI rerun is pending after the Click fix.

## Rejected / deferred
- Visual/screenshot grounding, XDM modeling, and mobile platforms — not required for web QA.
- Remainder of the enterprise CMP/audit engine beyond the shipped vertical slice: custom
  adapter plugins, more documented vendor state readers, multi-page/SPA consent journeys,
  GPP/TCF string decoding, and consent-aware tag-configuration joining.

## Policy

Any future feature or upgrade must check `AUDIT_FINDINGS.md` and this file before implementation. A blocked item is retried only when its external dependency is available; a rejected item needs new user evidence or a design change to reopen.
