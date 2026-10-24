from __future__ import annotations

import json

from click.testing import CliRunner
from pytagmanager import cli
from pytagmanager.control import (
    ConfigPayload,
    ControlPlaneService,
    FileStore,
    Tag,
    Trigger,
    Variable,
)
from pytagmanager.gtm import (
    analyze_container,
    gtm_to_payload,
    load_container,
    payload_to_gtm,
    write_container,
)


def _sample_export():
    return {
        "exportFormatVersion": 2,
        "containerVersion": {
            "tag": [
                {
                    "tagId": "1",
                    "name": "GA4 Purchase",
                    "type": "gaawe",
                    "firingTriggerId": ["1"],
                    "parameter": [
                        {"key": "eventName", "value": "purchase"},
                        {"key": "measurementId", "value": "G-ABC123"},
                    ],
                },
                {
                    "tagId": "2",
                    "name": "GA4 Purchase",
                    "type": "gaawe",
                    "firingTriggerId": ["1"],
                    "parameter": [
                        {"key": "eventName", "value": "purchase"},
                        {"key": "measurementId", "value": "G-ABC123"},
                    ],
                },
                {
                    "tagId": "3",
                    "name": "Broken",
                    "type": "gaawe",
                    "firingTriggerId": [],
                    "parameter": [{"key": "eventName", "value": "{{Missing Var}}"}],
                },
            ],
            "trigger": [
                {
                    "triggerId": "1",
                    "name": "Purchase",
                    "type": "CUSTOM_EVENT",
                    "customEventFilter": [
                        {
                            "type": "EQUALS",
                            "parameter": [
                                {"key": "arg0", "value": "{{_event}}"},
                                {"key": "arg1", "value": "purchase"},
                            ],
                        }
                    ],
                },
                {"triggerId": "2", "name": "Unused", "type": "PAGEVIEW"},
            ],
            "variable": [],
        },
    }


def test_analysis_finds_duplicates_unused_and_unresolved():
    findings = analyze_container(_sample_export())
    codes = {finding.code for finding in findings}
    assert {
        "duplicate_tag_name",
        "tag_without_trigger",
        "unresolved_variable",
        "trigger_without_tag",
        "duplicate_ga4_event_delivery",
        "duplicate_measurement_id",
    } <= codes
    for finding in findings:
        assert finding.severity in {
            "critical",
            "high",
            "medium",
            "low",
            "informational",
        }
        assert finding.confidence in {
            "confirmed",
            "high-confidence",
            "suspected",
            "unverified",
        }
        assert finding.evidence
        assert finding.remediation


def test_yaml_and_json_round_trip(tmp_path):
    json_path = write_container(_sample_export(), tmp_path / "container.json")
    yaml_path = write_container(_sample_export(), tmp_path / "container.yaml")
    assert json.loads(json_path.read_text())["exportFormatVersion"] == 2
    assert "containerVersion" in yaml_path.read_text()
    assert load_container(json_path)["exportFormatVersion"] == 2
    assert load_container(yaml_path)["exportFormatVersion"] == 2


def test_control_payload_round_trips_through_gtm_projection():
    trigger = Trigger.create(
        name="Purchase event",
        type="custom_event",
        conditions={
            "op": "all",
            "conditions": [{"op": "equals", "path": "event.name", "value": "purchase"}],
        },
    )
    variable = Variable.create(
        name="ecommerce.value",
        type="string",
        source="data_layer",
        source_ref="ecommerce.value",
    )
    tag = Tag.create(
        name="GA4 purchase",
        type="ga4_event",
        parameters={"eventName": "purchase", "value": "{{ecommerce.value}}"},
        trigger_ids=[trigger.trigger_id],
        variable_ids=[variable.variable_id],
    )
    payload = ConfigPayload(tags=(tag,), triggers=(trigger,), variables=(variable,))
    document = payload_to_gtm(payload)
    imported, warnings = gtm_to_payload(document)
    assert len(imported.tags) == 1
    assert len(imported.triggers) == 1
    assert len(imported.variables) == 1
    assert imported.triggers[0].type == "custom_event"
    assert imported.variables[0].source == "data_layer"
    assert imported.variables[0].source_ref == "ecommerce.value"
    assert imported.tags[0].trigger_ids
    assert not [warning for warning in warnings if "unknown trigger" in warning]


def test_cli_inspect_json_and_text(tmp_path):
    path = write_container(_sample_export(), tmp_path / "container.yaml")
    result = CliRunner().invoke(cli.main, ["gtm", "inspect", str(path), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["finding_count"] >= 5
    text = CliRunner().invoke(cli.main, ["gtm", "inspect", str(path)])
    assert text.exit_code == 0
    assert "duplicate_ga4_event_delivery" in text.output


def test_cli_export_and_import_as_drafts(tmp_path):
    service = ControlPlaneService(FileStore(tmp_path / "state"))
    service.create_container("GTM-ABC1234")
    trigger = Trigger.create(
        name="Purchase event",
        type="custom_event",
        conditions={
            "op": "all",
            "conditions": [{"op": "equals", "path": "event.name", "value": "purchase"}],
        },
    )
    tag = Tag.create(
        name="GA4 purchase",
        type="ga4_event",
        parameters={"eventName": "purchase"},
        trigger_ids=[trigger.trigger_id],
    )
    revision = service.create_revision(
        "GTM-ABC1234", ConfigPayload(tags=(tag,), triggers=(trigger,))
    )
    exported = tmp_path / "gtm.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        [
            "gtm",
            "export",
            "GTM-ABC1234",
            "--home",
            str(service.store.root),
            "--output",
            str(exported),
        ],
    )
    assert result.exit_code == 0, result.output
    assert exported.is_file()
    service.create_container("GTM-OTHER1")
    imported = runner.invoke(
        cli.main,
        [
            "gtm",
            "import",
            str(exported),
            "GTM-OTHER1",
            "--home",
            str(service.store.root),
            "--json",
        ],
    )
    assert imported.exit_code == 0, imported.output
    payload = json.loads(imported.output)
    assert payload["activated"] is False
    assert payload["object_counts"]["tags"] == 1
    revisions = service.list_revisions("GTM-OTHER1")
    assert len(revisions) == 1
    assert revisions[0].status == "draft"
    assert revision.config_version != revisions[0].config_version
