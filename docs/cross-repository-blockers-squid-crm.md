# Cross-Repository Blockers — PyTagManager ↔ Squid-CRM

Detailed specification of the PyTagManager → Squid-CRM integration blocker,
from the PyTagManager perspective. The shared context is documented in
`Mullassery/Squid-CRM/docs/cross-repository-blockers.md`; this file records the
PyTagManager side of the contract and what must change here to unblock it.

Reference pin: `twentyhq/twenty@08a0e5f1ee2e7db7c1e6ef3aeec9bcef731f4e98`
(Twenty server `2.50.0`).

## 1. The blocker

**Status:** OPEN — No direct Squid-CRM adapter or agreed findings schema/version.
Generic custom objects can store findings in Squid, but no Squid payload mapping
or custom-object schema contract is defined for findings output.

## 2. The two sides

| Aspect | PyTagManager (findings output) | Squid-CRM (destination) |
|--------|-------------------------------|-------------------------|
| Output | Tag findings, GTM diagnosis results, consent audits | Custom-object REST `/rest/{object}`, generic JSON GraphQL CRUD |
| Schema | Event v1 (`schema_version`, `event_id`, `event_name`, `timestamp`, `source`, `container_id`, `properties`, `subject`, `consent`, `correlation`) | Custom-object metadata (object + field definitions) |
| Activation path | Direct custom-object REST (no agreed schema) | Materialized physical tables + scalar/relation columns from metadata |
| Batch | Single findings records | Custom-object batch upsert (`/rest/{object}/upsert`) |
| Relationship | Findings reference tags/containers | Relation fields (MANY_TO_ONE) create UUID columns + reverse ONE_TO_MANY |
| Ownership | Browser/GTM tagging diagnosis; does not own CRM records | CRM system of record |

## 3. What must be agreed (PyTagManager side)

1. **Findings schema contract.** What finding fields (finding_id, tag_id,
   container_id, severity, confidence, etc.) map to Squid custom-object field
   definitions? No agreed findings schema/version exists in either repository.
2. **Custom-object schema.** What object name(s) will findings be written to in
   Squid? Must be defined before findings can be stored without ad-hoc fields.
3. **Batch/upsert.** Findings are typically single records, but batch ingestion
   may be needed. Squid's custom-object `/rest/{object}/upsert` supports this;
   batch strategy must be agreed.
4. **Event v1 alignment.** PyTagManager event v1 already has `event_id`,
   `correlation_id`, `consent`, and `subject` fields — these may overlap with
   Squid's idempotency and consent concerns. Alignment must be confirmed.

## 4. Evidence

**PyTagManager:**
- Event contract: `schemas/events/v1/event.schema.json`, `schema_version:
  "1.0"`, UUIDv4 event ID, RFC 3339 UTC timestamp, strict unknown-field
  rejection, 32 KiB event limit, sensitive-property denylist.
- `subject.id` maps to `anon:<event_id>` for events without a subject ID.
- `consent` object with `purposes`, `source`, `provenance` — relevant to the
  PyTagShield consent blocker.
- No direct Squid-CRM adapter or agreed findings schema/version.

**Squid-CRM:**
- Custom-object metadata writes create physical tables, scalar/relation columns,
  and generic REST CRUD — integration-tested.
- Custom-object batch upsert (`/rest/{object}/upsert`) is integration-tested.

## 5. Owner of next move

**PyTagManager** must define its findings output schema and agree on a
custom-object schema contract with Squid-CRM. Squid-CRM cannot pre-create
object/field metadata without knowing the shape.

## 6. Related blockers

- **PyTagShield + Squid:** consent decision contract — PyTagManager event v1
  already carries consent fields; alignment with Squid's consent model must be
  confirmed.
- **PyReverseETL + Squid:** activation payload + idempotency header — if
  findings flow through PyReverseETL to Squid, this blocker must be resolved
  first.
- **PyCustomerHub + Squid:** shared event-schema contract — PyTagManager →
  PyCustomerHub ingestion also needs an explicit mapping (separate concern).
