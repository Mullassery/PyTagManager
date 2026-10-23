# Squid findings contract v1

- **Status:** proposed PyTagManager-side contract. Not accepted or live-tested against Squid.
- **Contract ID:** `pytagmanager.squid.tag-finding.v1`
- **Owner:** PyTagManager for the findings schema; Squid-CRM for metadata acceptance and the write endpoint.
- **Scope:** PyTagManager findings only. Segments remain owned by ClusterAudienceKit.

## Why this exists

The cross-repo blocker register records that ClusterAudienceKit / PyTagManager had
no agreed Squid custom-object schema. PyTagManager can close its half by defining
a versioned findings object, stable record identity, and the lookup/upsert
sequence needed for idempotent writes.

This does **not** claim that Squid accepts the schema. It is a concrete contract
for Squid to accept or amend.

## Commands

Emit the object/field manifest:

```bash
pytagmanager squid manifest -o squid-findings-manifest.json
```

Map a diagnose JSON report to records and a write plan:

```bash
pytagmanager diagnose https://example.com --scenario checkout.yml --format json -o diagnose.json
pytagmanager squid findings \
  --input diagnose.json \
  --workspace-id 00000000-0000-4000-8000-000000000001 \
  -o squid-findings-plan.json
```

`squid findings` emits data only. It does not call Squid, create metadata, or
write records.

## Object contract

- Object: `tagManagerFinding` / `tagManagerFindings`
- Labels: `Tag Manager Finding` / `Tag Manager Findings`
- Icon: `IconAlertTriangle`
- Automatic Squid field: `name`
- Record schema: [`schemas/squid/v1/tag-finding.schema.json`](../schemas/squid/v1/tag-finding.schema.json)

| Field | Type | Required | Unique | Notes |
|---|---|---:|---:|---|
| `findingId` | TEXT | yes | yes | Stable `ptm_<24 hex>` identity |
| `ruleId` | TEXT | yes | no | Diagnostic rule/root-cause ID |
| `rootCause` | TEXT | yes | no | Root-cause slug |
| `severity` | TEXT | yes | no | `critical`, `warning`, `unknown` |
| `confidence` | TEXT | yes | no | PyTagManager confidence label |
| `message` | TEXT | yes | no | Plain-language finding |
| `recommendation` | TEXT | yes | no | Actionable remediation |
| `pageUrl` | TEXT | no | no | Query string and fragment removed |
| `selector` | TEXT | no | no | Interaction selector |
| `tagId` | TEXT | no | no | GTM tag ID when available |
| `containerId` | TEXT | no | no | GTM container ID when available |
| `sourceEvent` | TEXT | no | no | Business/dataLayer event |
| `source` | TEXT | yes | no | Report source, e.g. `diagnose` |
| `schemaVersion` | TEXT | yes | no | Const `"1"` |

Raw diagnostic details, dataLayer payloads, consent strings and PII are not
copied into records. Details are used only to derive stable identity and selected
safe fields.

## Write strategy

Squid's custom-object `/upsert` matches on Squid record `id`, not on an arbitrary
unique field. The contract therefore defines a two-phase sequence:

1. Look up each `findingId`:
   `GET /rest/tagManagerFindings?filter=findingId[eq]:<findingId>&limit=1`
2. Add the Squid `id` to records that already exist.
3. `POST /rest/tagManagerFindings/upsert` with `{"records": [...]}`.
4. Retry an identical request with the same `Idempotency-Key` on transient
   failure.

The generated plan includes:

- `Idempotency-Key: pytagmanager-findings-v1:<sha256(canonical body)>`
- `X-Correlation-Id: ptm-<plan hash>`
- `Content-Type: application/json`
- No credentials. The caller supplies a Squid API key with Update capability.

The idempotency key is stable for an identical batch body. If finding content
changes, the body hash changes; the lookup by stable `findingId` is what prevents
duplicates on update.

## Squid acceptance checklist

1. Create the object and fields from `metadata_operations`.
2. Enforce `findingId` uniqueness per workspace.
3. Confirm the REST filter and `/upsert` behavior against a live/test workspace.
4. Confirm which API key capability is required and how it is provisioned.
5. Run a live integration test with create, update, retry and conflict cases.
6. Decide whether batch size should be capped beyond the caller's plan.

Until these pass, the integration status is **PARTIAL**, not verified.

## Limitations

- No live Squid workspace, database or API key was used.
- No Squid metadata was created by PyTagManager.
- No HTTP client is bundled for the write plan.
- Segment/audience custom objects are not covered; ClusterAudienceKit owns them.
- Generated GraphQL types for custom objects remain a Squid limitation; REST is
  the interim path.
- Findings are evidence, not a consent decision, compliance verdict or delivery
  proof.
