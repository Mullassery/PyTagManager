from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner
from pytagmanager.cli import main
from pytagmanager.squid import (
    CONTRACT_ID,
    OBJECT_NAME_PLURAL,
    SquidContractError,
    build_finding_manifest,
    build_findings_plan,
    diagnosis_to_finding_record,
    recommendation_for_root_cause,
    validate_finding_record,
)


def _finding(**overrides):
    finding = {
        "journey_id": "journey-1",
        "event": "add_to_cart",
        "severity": "critical",
        "status": "failed",
        "root_cause": "missing_datalayer_event",
        "message": "User interaction occurred but no dataLayer event fired.",
        "confidence": "Confirmed",
        "details": {
            "page_url": "https://example.com/cart?token=secret#x",
            "selector": "#buy",
        },
    }
    finding.update(overrides)
    return finding


def _report():
    return {
        "schema_version": 1,
        "diagnostics": [
            _finding(),
            {
                "journey_id": "journey-2",
                "event": "page_view",
                "severity": "healthy",
                "status": "healthy",
                "root_cause": "none",
                "message": "Tracking behaved as expected.",
                "confidence": "Confirmed",
                "details": {},
            },
        ],
        "additional_findings": [
            {
                "root_cause": "pii_leak_detected",
                "severity": "warning",
                "confidence": "Highly likely",
                "message": "Sensitive-looking data appeared in a dataLayer payload.",
                "details": {
                    "tag_id": "10",
                    "container_id": "GTM-ABC1234",
                    "page_url": "https://example.com/checkout?email=jane@example.com",
                },
            }
        ],
    }


def test_manifest_defines_a_single_versioned_finding_object():
    manifest = build_finding_manifest()
    assert manifest["contract"] == CONTRACT_ID
    assert manifest["status"] == "proposed"
    assert manifest["object"]["nameSingular"] == "tagManagerFinding"
    assert manifest["object"]["namePlural"] == OBJECT_NAME_PLURAL
    names = [field["name"] for field in manifest["fields"]]
    assert len(names) == len(set(names))
    by_name = {field["name"]: field for field in manifest["fields"]}
    assert by_name["findingId"]["isUnique"] is True
    assert by_name["findingId"]["isNullable"] is False
    assert all(field["type"] == "TEXT" for field in manifest["fields"])
    assert manifest["upsert"]["match_field"] == "findingId"
    assert manifest["upsert"]["lookup"]["path"] == "/rest/tagManagerFindings"
    identifier = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
    for name in [
        manifest["object"]["nameSingular"],
        manifest["object"]["namePlural"],
        *names,
    ]:
        assert identifier.fullmatch(name), name
    for operation in manifest["metadata_operations"]["create_fields"]:
        assert operation["field"]["objectMetadataId"] == "<created-object-id>"


def test_finding_record_maps_to_the_contract_without_raw_details_or_query_strings():
    record = diagnosis_to_finding_record(_finding())
    validate_finding_record(record)
    assert record["findingId"].startswith("ptm_")
    assert record["rootCause"] == "missing_datalayer_event"
    assert record["pageUrl"] == "https://example.com/cart"
    assert record["selector"] == "#buy"
    assert record["recommendation"] == recommendation_for_root_cause("missing_datalayer_event")
    serialized = json.dumps(record)
    assert "secret" not in serialized
    assert "jane@example.com" not in serialized
    assert "details" not in record


def test_finding_identity_is_stable_across_runs_and_changes_with_the_finding():
    first = diagnosis_to_finding_record(_finding())
    rerun = diagnosis_to_finding_record(_finding(journey_id="a-new-random-journey-id"))
    changed = diagnosis_to_finding_record(_finding(message="A different finding message."))
    assert first["findingId"] == rerun["findingId"]
    assert first["findingId"] != changed["findingId"]


def test_plan_skips_healthy_journeys_and_has_stable_idempotency():
    plan = build_findings_plan(_report(), workspace_id="workspace-1")
    assert plan["status"] == "proposed"
    assert len(plan["records"]) == 2
    assert {record["rootCause"] for record in plan["records"]} == {
        "missing_datalayer_event",
        "pii_leak_detected",
    }
    assert plan["request"]["path"] == "/rest/tagManagerFindings/upsert"
    assert plan["request"]["headers"]["Idempotency-Key"].startswith("pytagmanager-findings-v1:")
    assert plan["write_strategy"]["match_field"] == "findingId"
    again = build_findings_plan(_report(), workspace_id="workspace-1")
    assert (
        plan["request"]["headers"]["Idempotency-Key"]
        == again["request"]["headers"]["Idempotency-Key"]
    )
    assert plan["plan_id"] == again["plan_id"]


def test_record_matches_the_published_json_schema_required_shape():
    schema = json.loads(
        (
            Path(__file__).parents[2] / "schemas" / "squid" / "v1" / "tag-finding.schema.json"
        ).read_text()
    )
    record = diagnosis_to_finding_record(_finding())
    assert set(schema["required"]) <= set(record)
    assert set(record) <= set(schema["properties"])
    assert schema["properties"]["findingId"]["pattern"] == "^ptm_[a-f0-9]{24}$"


def test_clean_report_emits_no_write_request():
    plan = build_findings_plan(
        {
            "schema_version": 1,
            "diagnostics": [
                {
                    "journey_id": "healthy",
                    "event": "page_view",
                    "severity": "healthy",
                    "status": "healthy",
                    "root_cause": "none",
                    "message": "ok",
                    "confidence": "Confirmed",
                }
            ],
            "additional_findings": [],
        }
    )
    assert plan["records"] == []
    assert plan["request"] is None


def test_record_validation_rejects_query_strings_and_unknown_severity():
    record = diagnosis_to_finding_record(_finding())
    record["pageUrl"] = "https://example.com/cart?token=secret"
    with pytest.raises(SquidContractError, match="query string"):
        validate_finding_record(record)

    record = diagnosis_to_finding_record(_finding())
    record["severity"] = "severe"
    with pytest.raises(SquidContractError, match="severity"):
        validate_finding_record(record)


def test_plan_rejects_non_object_reports():
    with pytest.raises(SquidContractError, match="must be an object"):
        build_findings_plan([])


def test_squid_cli_manifest_and_findings_plan(tmp_path):
    runner = CliRunner()
    manifest_result = runner.invoke(main, ["squid", "manifest"])
    assert manifest_result.exit_code == 0, manifest_result.output
    manifest = json.loads(manifest_result.output)
    assert manifest["contract"] == CONTRACT_ID

    report_path = tmp_path / "diagnose.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    plan_result = runner.invoke(
        main,
        [
            "squid",
            "findings",
            "--input",
            str(report_path),
            "--workspace-id",
            "workspace-1",
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    plan = json.loads(plan_result.output)
    assert plan["workspace_id"] == "workspace-1"
    assert len(plan["records"]) == 2
