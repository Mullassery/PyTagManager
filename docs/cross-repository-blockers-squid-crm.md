# Cross-Repository Blockers — PyTagManager ↔ Squid-CRM

Detailed specification of the PyTagManager → Squid-CRM integration blocker,
from the PyTagManager perspective. The shared context is documented in
`Mullassery/Squid-CRM/docs/cross-repository-blockers.md`; this file records the
PyTagManager side of the contract and what must change here to unblock it.

Reference pin: `twentyhq/twenty@08a0e5f1ee2e7db7c1e6ef3aeec9bcef731f4e98`
(Twenty server `2.50.0`).

## 1. The blocker

**Status:** PARTIAL — PyTagManager has defined a versioned findings schema and
write plan. Squid has not accepted the metadata contract, and no live write was
run. Generic custom objects can store findings, but this is not yet an
integration.

## 2. The two sides

| Aspect | PyTagManager (findings output) | Squid-CRM (destination) |
|--------|-------------------------------|-------------------------|
| Output | Tag findings, GTM diagnosis results, consent audits | Custom-object REST `/rest/{object}`, generic JSON GraphQL CRUD |
| Schema | `pytagmanager.squid.tag-finding.v1` (`tagManagerFinding` records) | Custom-object metadata (object + field definitions) |
| Activation path | Proposed lookup + `/rest/tagManagerFindings/upsert` plan; no HTTP client | Materialized physical tables + scalar/relation columns from metadata |
| Batch | Single findings records | Custom-object batch upsert (`/rest/{object}/upsert`) |
| Relationship | Findings reference tags/containers | Relation fields (MANY_TO_ONE) create UUID columns + reverse ONE_TO_MANY |
| Ownership | Browser/GTM tagging diagnosis; does not own CRM records | CRM system of record |

## 3. PyTagManager-side contract (defined)

1. **Findings schema.** `tagManagerFinding` v1 with stable `findingId`, rule/root
   cause, severity, confidence, message, recommendation, optional page/selector/
   tag/container context, source and schema version. See
   `schemas/squid/v1/tag-finding.schema.json`.
2. **Custom-object metadata.** Object/field manifest emitted by
   `pytagmanager squid manifest`, including Squid field types, uniqueness and
   searchability.
3. **Batch/upsert.** `pytagmanager squid findings` emits records plus a two-phase
   `findingId` lookup and `/rest/tagManagerFindings/upsert` plan, with a
   deterministic `Idempotency-Key` based on the canonical batch body.
4. **Safety.** Raw diagnostic details, dataLayer payloads, query strings and PII
   are not copied into records.

## 4. What remains (Squid side)

1. Accept or amend the object/field metadata contract.
2. Confirm the `findingId` uniqueness and REST filter behavior on a live/test
   workspace.
3. Confirm API-key capability requirements for create/update.
4. Run a live integration test covering create, update, retry and conflict.
5. Decide whether a batch-size cap is needed.

## 5. Evidence

**PyTagManager:**
- `python/pytagmanager/squid/findings.py`: manifest, record mapping, validation,
  stable finding identity and write plan.
- `pytagmanager squid manifest` / `pytagmanager squid findings` CLI.
- `schemas/squid/v1/tag-finding.schema.json` and
  `docs/examples/squid-findings-plan.json`.
- `tests/python/test_squid_findings.py` (9 tests, no live Squid call).
- `docs/SQUID_FINDINGS.md` documents the contract and its limitations.
- No Squid metadata was created; no live write was run.

**Squid-CRM:**
- Custom-object metadata writes create physical tables, scalar/relation columns,
  and generic REST CRUD — integration-tested.
- Custom-object batch upsert (`/rest/{object}/upsert`) is integration-tested.

## 6. Owner of next move

**Squid-CRM** must accept or amend the proposed metadata contract and run the
live write test. **PyTagManager** owns the schema and can revise it if Squid
requires different field names/types or a stricter idempotency strategy.

## 7. Related blockers

- **PyTagShield + Squid:** consent decision contract — PyTagManager findings do
  not encode consent decisions; PyTagShield remains the authority.
- **PyReverseETL + Squid:** activation payload + idempotency header — if
  findings flow through PyReverseETL to Squid, this blocker must be resolved
  first.
- **PyCustomerHub + Squid:** shared event-schema contract — PyTagManager →
  PyCustomerHub ingestion also needs an explicit mapping (separate concern).
