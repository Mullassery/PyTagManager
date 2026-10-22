# CMP audit

`pytagmanager cmp audit` collects evidence about consent management on one
page: which consent platform is present, what consent state is readable, which
analytics/advertising requests fired before or after a consent choice, and
whether a choice survived a reload. It is an evidence tool, not a legal
compliance determination.

## Safety model

- **Read-only by default.** The command never clicks or submits a consent
  choice unless both `--consent-action` and `--authorize-consent-interaction`
  are supplied.
- **Only test environments you control.** Authorizing an interaction means
  exactly that. Do not use it to submit real consent choices on a production
  site or on behalf of another person.
- **No cookie values.** Reports include cookie names and metadata only. Request
  URLs are stripped of query strings before they become evidence.
- **No compliance score.** A visible banner is not treated as proof of
  enforcement, and a missing CMP signature is not treated as proof of absence.
- **No PyTagShield dependency.** This module neither imports nor requires
  PyTagShield, and does not claim runtime blocking/enforcement.

## Usage

Read-only discovery and pre-consent evidence:

```bash
pytagmanager cmp audit https://staging.example.com
```

JSON for another tool or CI artifact:

```bash
pytagmanager cmp audit https://staging.example.com \
  --format json -o cmp-audit.json
```

Exercise a consent control in an isolated test session:

```bash
pytagmanager cmp audit https://staging.example.com \
  --consent-action reject \
  --authorize-consent-interaction \
  --reload-after-consent \
  --format json -o cmp-reject-audit.json
```

If the vendor's default selector does not match the deployed UI, pass an
explicit selector (repeatable):

```bash
pytagmanager cmp audit https://staging.example.com \
  --consent-action accept \
  --authorize-consent-interaction \
  --accept-selector '[data-testid="consent-accept"]'
```

Without `--authorize-consent-interaction`, an action is refused before a
browser is launched.

## What is collected

| Signal | Source | Notes |
| --- | --- | --- |
| Vendor script, inline marker, global | rendered DOM / page JS | Detects supported adapters |
| Vendor network endpoints | browser network events | Bounded and query-stripped |
| Cookie names and metadata | browser cookie store | Values never serialized |
| Consent Mode `default` / `update` | existing `agent.js` consent capture | Mapped to analytics/advertising/preferences |
| Cookiebot category state | documented `window.Cookiebot.consent` | Only direct vendor API reader in this slice |
| Pre/post-choice requests | browser network events | Ordered against the explicit action timestamp |
| Reload persistence | second page load | Only when `--reload-after-consent` is used |

Normalized categories are `necessary`, `preferences`, `analytics`,
`advertising`, and `other`. Vendor-specific category names are preserved in
evidence; they are not presented as a legal category mapping.

## Supported adapters

`Cookiebot`, `OneTrust`, `Usercentrics`, `Didomi`, `Quantcast Choice`,
`TrustArc`, `Osano`, and `Google Funding Choices`.

Adapter detection is signature-based. Only Cookiebot currently has a direct,
documented consent-state reader. For the others, cookie presence is reported
without decoding it, and their click selectors are best-effort defaults that
must be verified against the deployed version. A custom or unsupported CMP is
reported as undetected rather than guessed.

## Findings

Findings have a stable `rule_id`, severity, confidence, evidence, remediation,
detection method, and component. Current rules include:

- `cmp.tracking_before_consent.*`
- `cmp.tracking_after_reject`
- `cmp.tracking_without_supported_cmp`
- `cmp.no_supported_cmp_detected`
- `cmp.consent_state_unavailable`
- `cmp.consent_cookie_without_detection`
- `cmp.consent_control_unavailable`
- `cmp.accept_not_effective`
- `cmp.reject_not_effective`
- `cmp.consent_signal_conflict`
- `cmp.consent_not_persisted`
- `cmp.consent_persistence_unverified`
- `cmp.google_consent_mode_missing`

Confidence is intentionally conservative. A request observed before any
explicit interaction with a readable `denied` state is high-confidence. If the
state is unknown, the same observation is only a lead (`suspected`) because a
prior consent record could exist.

## JSON schema

The v1 schema is at
[`schemas/cmp/v1/audit-report.schema.json`](../schemas/cmp/v1/audit-report.schema.json).
It deliberately has no field for raw cookie values or request query strings.
A sample is at
[`docs/examples/cmp-audit-report.json`](examples/cmp-audit-report.json).

## Python API

```python
from pytagmanager.cmp import CmpAuditOptions, CmpAuditRunner

report = CmpAuditRunner(
    CmpAuditOptions(wait_seconds=1.0)
).run("https://staging.example.com")

print(report.detections)
print(report.findings)

# Only with explicit authorization in a test environment you control:
report = CmpAuditRunner().run(
    "https://staging.example.com",
    consent_action="reject",
    authorize_consent_interaction=True,
)
```

## Limitations

- Browser-side observation cannot prove server-side consent enforcement.
- Logged-in states, cross-device consent, GPC/DNS, and mobile app consent were
  not tested.
- A cookie's presence does not prove which categories were granted.
- Vendor consent APIs and selectors can change between deployments.
- Only one page and one consent lifecycle are exercised per run.
- Reports are evidence and remediation inputs, not legal advice or a
  certification of compliance.
