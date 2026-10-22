# Tracking-regression CI

A checked-in workflow (`.github/workflows/tracking-regression.yml`) runs daily or
on `workflow_dispatch`, stores health history in Actions cache, and exits
non-zero on a regression. Set the `TRACKING_TARGET_URL` repository variable (or
pass the `url` input) and optionally `TRACKING_ALERT_WEBHOOK`.

The equivalent standalone workflow is:

```yaml
name: tracking-regression
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

jobs:
  diagnose:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "pytagmanager[diagnostics]"
      - run: playwright install --with-deps chromium
      - name: Restore tracking history
        uses: actions/cache@v4
        with:
          path: .pytagmanager/health.json
          key: tracking-history-${{ github.ref_name }}
          restore-keys: tracking-history-
      - name: Diagnose
        env:
          TARGET_URL: ${{ vars.TRACKING_TARGET_URL }}
          ALERT_WEBHOOK: ${{ secrets.TRACKING_ALERT_WEBHOOK }}
        run: |
          mkdir -p .pytagmanager
          pytagmanager diagnose "$TARGET_URL" \
            --site-wide \
            --max-pages 50 \
            --history .pytagmanager/health.json \
            --alert-threshold 5 \
            --fail-on-regression \
            ${ALERT_WEBHOOK:+--alert-webhook "$ALERT_WEBHOOK"} \
            -o .pytagmanager/report.json --format json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: tracking-report
          path: .pytagmanager/report.json
```

Notes:

- `--history` appends the current score after comparing; cache the history file
  or the first run will always look like "no previous data".
- `--fail-on-regression` requires `--history`.
- The webhook is optional; without it the job still fails, which is usually
  enough for GitHub's notification settings.

## CMP audit artifacts

Read-only CMP evidence is safe to collect from a staging URL. Authorized consent
interaction is a separate, explicit opt-in and should only target an isolated
environment you control — never a shared production site.

```yaml
      - name: CMP evidence
        run: |
          pytagmanager cmp audit "$STAGING_URL" \
            --format json -o cmp-audit.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: cmp-audit
          path: cmp-audit.json
```

The report contains stable findings and limitations, but no compliance score.
Cookie values and request query strings are excluded. If you intentionally test
a choice, add `--consent-action reject --authorize-consent-interaction` and run
against a disposable test environment. See [`CMP_AUDIT.md`](CMP_AUDIT.md).

## Lighthouse CI budgets

`lighthouse-ci` runs Lighthouse several times and evaluates explicit budgets
against the **median**, not a lucky single run. It never invents a performance
verdict when budgets are absent or too few runs complete.

```yaml
name: lighthouse-budget
on:
  workflow_dispatch:
  schedule:
    - cron: "0 7 * * *"

jobs:
  lighthouse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: npm install -g lighthouse
      - run: pip install "pytagmanager[diagnostics]"
      - name: Repeated Lighthouse audit
        env:
          TARGET_URL: ${{ vars.LIGHTHOUSE_TARGET_URL }}
        run: |
          pytagmanager lighthouse-ci "$TARGET_URL" \
            --runs 5 \
            --min-runs 3 \
            --budget lcp_ms=2500 \
            --budget tbt_ms=200 \
            --budget cls=0.1 \
            --budget performance=0.9 \
            --fail-on-budget \
            --format json -o lighthouse-ci.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: lighthouse-ci-report
          path: lighthouse-ci.json
```

Exit codes:

- `0` — enough runs completed; any supplied budgets passed.
- `1` — a supplied budget failed, or its metric was absent (absent is not a
  pass).
- `2` — fewer than `--min-runs` completed, or some runs failed and
  `--allow-partial` was not supplied.

Lighthouse is a lab measurement. The report records the version, every sample,
observed range, confidence and limitations; it does not claim field data or
guarantee that a fast page sends tags correctly.
