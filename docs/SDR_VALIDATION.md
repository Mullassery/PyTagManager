# SDR-driven validation

- **Status:** implemented v1 for observed dataLayer events and parameters.
- **Inputs:** JSON or CSV Solution Design Reference plus a `diagnose` run with a scenario or crawl.
- **Output:** pass/fail checks, alignment score, missing/mismatched fields and layer-specific recommendations.

This validates an uploaded SDR against runtime evidence. It does not replace the
CMP audit and does not produce a compliance verdict.

## Command

```bash
pytagmanager diagnose https://example.com \
  --scenario checkout.yml \
  --sdr docs/examples/sdr-checkout.json \
  --format json \
  -o diagnose.json
```

Text output appends an `SDR Alignment` section. JSON output adds a top-level
`sdr_alignment` object. Add `--fail-on-sdr-mismatch` to exit 1 when any check
fails (for CI).

Without `--scenario`, `diagnose` crawls and auto-generates interactions. The SDR
can only validate events those interactions actually exercise.

## Input formats

Canonical JSON:

```json
{
  "schema_version": 1,
  "name": "Checkout SDR",
  "events": [
    {
      "event_name": "add_to_cart",
      "page_contains": "/cart",
      "selector": "[data-testid='add-to-cart']",
      "require_network": true,
      "parameters": [
        {"name": "value", "type": "number", "required": true},
        {"name": "currency", "type": "string", "required": true, "allowed": ["USD", "EUR"]},
        {"name": "items", "type": "array", "required": true},
        {"name": "coupon", "type": "string", "required": false}
      ]
    }
  ]
}
```

JSON schema: [`schemas/sdr/v1/sdr.schema.json`](../schemas/sdr/v1/sdr.schema.json)

CSV columns:

| Column | Meaning |
|---|---|
| `event_name` | Required dataLayer event |
| `parameter_name` | Optional parameter; repeat the event row per parameter |
| `type` | `any`, `string`, `number`, `integer`, `boolean`, `array`, `object`, or a `|`-separated union |
| `required` | Defaults to `true` |
| `allowed_values` | Optional `|`-separated allow-list |
| `page_contains` | Optional URL substring condition |
| `selector` | Optional interaction selector condition |
| `require_network` | Require some network request in the matching journey |

Example: [`docs/examples/sdr-checkout.csv`](examples/sdr-checkout.csv)

## What is checked

- event presence by exact dataLayer event name;
- required parameter presence;
- parameter type (boolean is not treated as an integer/number);
- allowed values when declared;
- optional page and interaction-selector conditions;
- duplicate dataLayer firing in one interaction;
- optional network-request presence in the matching journey.

Alignment score is passed checks divided by total evaluated checks. A missing
event is one failed check; its parameters are not separately scored. Parameter
values are never serialized in reports; only presence, type and allow-list
outcomes are reported.

## What is not checked

- GA4, Adobe, Segment or other destination parameter equivalence.
- Server-side delivery or Consent Mode enforcement.
- Events not exercised by the current scenario/crawl.
- Legal or regulatory compliance.
- Network request correctness beyond "a request was observed" when
  `require_network` is set.

The full limitation list is included in every JSON/text report.
