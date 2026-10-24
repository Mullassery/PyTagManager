# PyTagManager - Use Cases

## Overview

**Find out why a tag didn't fire — and what to fix — without stepping through GTM Preview one interaction at a time.** PyTagManager is an open-source debugging and implementation-intelligence toolkit for Google Tag Manager. It reads your GTM container, drives the real site in a real browser, and correlates the full chain:

## Use Cases

- **A tag stopped firing after a release.** Run `diagnose --site-wide --history health.json` and compare the failing template against the previous run.
- **You are migrating or auditing GTM.** Inspect the export with `gtm inspect`, crawl the site with `crawl --export gtm`, and review the delta with `gtm-plan` before touching production.
- **You need to prove consent actually blocks tracking.** Use `cmp audit` to capture pre/post-choice requests and reload persistence without making a compliance claim.
- **A vendor script looks expensive.** Use `perf --isolate` to block it plus its downstream dependencies and re-measure the same page.
- **A tracking bug needs a regression test.** Turn findings into `--test-candidates`, review them, then formalize the useful ones as Playwright tests.
- **The implementation drifted from the analytics spec.** Run `diagnose --sdr sdr.json --fail-on-sdr-mismatch` in CI and fail on missing events, fields, types or firing conditions.

## Common Scenarios

- Development and testing with PyTagManager
- Integration into existing workflows
- Exploration and prototyping

