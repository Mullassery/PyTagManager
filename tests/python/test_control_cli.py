from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from pytagmanager import cli
from pytagmanager.control import Tag


@pytest.fixture
def runner():
    return CliRunner()


def _create(runner, home, container_id="GTM-ABC1234", name=None):
    args = ["container", "create", "--id", container_id, "--home", str(home), "--json"]
    if name is not None:
        args += ["--name", name]
    return runner.invoke(cli.main, args)


def test_container_create_and_show_with_json(runner, tmp_path):
    created = _create(runner, tmp_path, name="Web")
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    assert payload["container_id"] == "GTM-ABC1234"
    assert payload["name"] == "Web"

    shown = runner.invoke(
        cli.main,
        ["container", "show", "--id", "GTM-ABC1234", "--home", str(tmp_path), "--json"],
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["container_id"] == "GTM-ABC1234"


def test_container_list_reports_containers(runner, tmp_path):
    assert _create(runner, tmp_path).exit_code == 0
    listed = runner.invoke(cli.main, ["container", "list", "--home", str(tmp_path)])
    assert listed.exit_code == 0
    assert "GTM-ABC1234" in listed.output


def test_duplicate_container_id_exits_with_error(runner, tmp_path):
    assert _create(runner, tmp_path).exit_code == 0
    duplicate = _create(runner, tmp_path, "gtm-abc1234")
    assert duplicate.exit_code != 0
    assert "already exists" in duplicate.output


def test_revision_create_list_and_validate(runner, tmp_path):
    assert _create(runner, tmp_path).exit_code == 0
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps({"tags": [Tag.create(name="Purchase", type="ga4_event").to_dict()]}),
        encoding="utf-8",
    )
    created = runner.invoke(
        cli.main,
        [
            "config",
            "revision-create",
            "GTM-ABC1234",
            "--payload",
            str(payload_path),
            "--home",
            str(tmp_path),
            "--json",
        ],
    )
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["revision_number"] == 1

    listed = runner.invoke(
        cli.main,
        ["config", "revision-list", "GTM-ABC1234", "--home", str(tmp_path)],
    )
    assert listed.exit_code == 0
    assert "draft" in listed.output

    validated = runner.invoke(
        cli.main,
        ["container", "validate", "--id", "GTM-ABC1234", "--home", str(tmp_path), "--json"],
    )
    assert validated.exit_code == 0, validated.output
    report = json.loads(validated.output)
    assert report["revision_count"] == 1
    assert report["payload_objects"] == 1


def test_expected_parent_mismatch_exits_with_error(runner, tmp_path):
    assert _create(runner, tmp_path).exit_code == 0
    runner.invoke(cli.main, ["config", "revision-create", "GTM-ABC1234", "--home", str(tmp_path)])
    mismatch = runner.invoke(
        cli.main,
        [
            "config",
            "revision-create",
            "GTM-ABC1234",
            "--expected-parent",
            "00000000-0000-4000-8000-000000000000",
            "--home",
            str(tmp_path),
        ],
    )
    assert mismatch.exit_code != 0
    assert "expected parent" in mismatch.output


def test_config_export_then_import_as(runner, tmp_path):
    assert _create(runner, tmp_path).exit_code == 0
    runner.invoke(cli.main, ["config", "revision-create", "GTM-ABC1234", "--home", str(tmp_path)])
    export_path = tmp_path / "export.json"
    exported = runner.invoke(
        cli.main,
        [
            "config",
            "export",
            "GTM-ABC1234",
            "--output",
            str(export_path),
            "--home",
            str(tmp_path),
        ],
    )
    assert exported.exit_code == 0, exported.output
    assert export_path.exists()

    other_home = tmp_path / "other"
    imported = runner.invoke(
        cli.main,
        [
            "config",
            "import",
            str(export_path),
            "--as",
            "GTM-COPY123",
            "--home",
            str(other_home),
            "--json",
        ],
    )
    assert imported.exit_code == 0, imported.output
    result = json.loads(imported.output)
    assert result["created"] is True
    assert result["container"]["container_id"] == "GTM-COPY123"


def test_import_rejects_non_json_file(runner, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    result = runner.invoke(
        cli.main, ["config", "import", str(bad), "--home", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "not valid JSON" in result.output
