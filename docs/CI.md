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
