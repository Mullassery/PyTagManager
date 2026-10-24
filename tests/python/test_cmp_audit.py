"""CMP audit tests: deterministic adapter/rule tests plus real local-browser
evidence tests against fixtures. No live third-party site is contacted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from pytagmanager.cli import main
from pytagmanager.cmp.adapters import (
    CookiebotAdapter,
    DidomiAdapter,
    OneTrustAdapter,
    detect_adapters,
    extract_signals,
    google_categories_from_mode,
    merge_consent_states,
    parse_google_consent_mode,
    read_gpp_consent,
    read_tcf_consent,
    tcf_categories_from_purposes,
)
from pytagmanager.cmp.collector import (
    CmpAuditAuthorizationError,
    CmpAuditOptions,
    CmpAuditRunner,
    _classify_request,
)
from pytagmanager.cmp.models import (
    CmpDetection,
    ConsentLifecycle,
    ConsentState,
    CookieMetadata,
    RequestObservation,
    dedupe_findings,
    sanitize_url,
)
from pytagmanager.cmp.plugins import (
    AdapterFileError,
    load_adapter_file,
    load_adapter_files,
)
from pytagmanager.cmp.report import render_cmp_audit_report
from pytagmanager.cmp.rules import analyze_cmp
from pytagmanager.observability.events import TrackingEvent

_SCHEMA_PATH = Path(__file__).parents[2] / "schemas" / "cmp" / "v1" / "audit-report.schema.json"


class _FakeSession:
    def __init__(self, result):
        self.result = result

    def evaluate(self, expression, arg=None):
        return self.result


def _signals(html: str, *, cookies=(), globals_present=(), network=()):
    return extract_signals(
        html=html,
        cookie_names=cookies,
        globals_present=globals_present,
        network_urls=network,
    )


@pytest.mark.parametrize(
    "adapter_id,markup",
    [
        ("cookiebot", '<script src="https://consent.cookiebot.com/uc.js"></script>'),
        (
            "onetrust",
            '<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"></script>',
        ),
        (
            "usercentrics",
            '<script src="https://app.usercentrics.eu/browser-ui/latest/loader.js"></script>',
        ),
        ("didomi", '<script src="https://sdk.privacy-center.org/loader.js"></script>'),
        (
            "quantcast",
            '<script src="https://quantcast.mgr.consensu.org/choice/x/choice.js"></script>',
        ),
        (
            "trustarc",
            '<script src="https://consent.trustarc.com/notice?domain=x"></script>',
        ),
        ("osano", '<script src="https://cmp.osano.com/abc/osano.js"></script>'),
        (
            "google-funding-choices",
            '<script src="https://fundingchoicesmessages.google.com/i/x"></script>',
        ),
    ],
)
def test_known_cmp_script_signatures_are_detected(adapter_id, markup):
    detections = detect_adapters(_signals(f"<html><head>{markup}</head></html>"))
    assert adapter_id in {item.adapter_id for item in detections}


def test_cmp_global_and_cookie_evidence_are_retained():
    detections = detect_adapters(
        _signals(
            "<html><body>nothing vendor-specific</body></html>",
            cookies=("OptanonConsent",),
            globals_present=("OneTrust",),
        )
    )
    onetrust = next(item for item in detections if item.adapter_id == "onetrust")
    assert onetrust.confidence == "confirmed"
    assert {item.kind for item in onetrust.evidence} >= {"global", "cookie"}
    assert "consent_controls" in onetrust.capabilities


def test_unknown_markup_is_not_misclassified_as_a_cmp():
    detections = detect_adapters(
        _signals("<html><body><button>Accept cookies</button></body></html>")
    )
    assert detections == ()


def test_cookiebot_documented_consent_api_is_read_and_mapped():
    adapter = CookiebotAdapter()
    state = adapter.read_consent(
        _FakeSession(
            {
                "necessary": True,
                "preferences": False,
                "statistics": True,
                "marketing": False,
            }
        )
    )
    assert state is not None
    assert state.confidence == "confirmed"
    assert state.category("necessary") is True
    assert state.category("preferences") is False
    assert state.category("analytics") is True
    assert state.category("advertising") is False


def test_google_consent_mode_default_and_update_are_merged_without_claiming_more():
    events = (
        TrackingEvent.create(
            source="consent",
            event_type="consent_change",
            event_name="default",
            payload={"ad_storage": "denied", "analytics_storage": "denied"},
        ),
        TrackingEvent.create(
            source="consent",
            event_type="consent_change",
            event_name="update",
            payload={"analytics_storage": "granted"},
        ),
    )
    state = parse_google_consent_mode(events)
    assert state is not None
    assert state.google_mode["analytics_storage"] == "granted"
    assert state.category("analytics") is True
    assert state.category("advertising") is False
    assert state.category("preferences") is None


def test_google_mode_mixed_advertising_signals_are_left_unknown():
    categories = google_categories_from_mode(
        {
            "ad_storage": "granted",
            "ad_user_data": "denied",
            "ad_personalization": "denied",
        }
    )
    assert categories["advertising"] is None


def test_cookie_presence_is_not_decoded_into_granted_categories():
    CmpDetection(
        adapter_id="cookiebot",
        vendor="Cookiebot",
        adapter_contract_version="1",
        confidence="confirmed",
    )
    state = merge_consent_states(
        [
            ConsentState(
                sources=("cookie_presence",),
                categories={
                    "necessary": None,
                    "preferences": None,
                    "analytics": None,
                    "advertising": None,
                    "other": None,
                },
                confidence="unverified",
            )
        ]
    )
    assert not state.has_categories
    assert state.category("analytics") is None


def _state(**categories):
    base = {
        "necessary": True,
        "preferences": None,
        "analytics": None,
        "advertising": None,
        "other": None,
    }
    base.update(categories)
    return ConsentState(
        sources=("google_consent_mode",),
        categories=base,
        google_mode={"analytics_storage": "denied"},
        confidence="confirmed",
    )


def _request(
    category="analytics",
    phase="initial",
    url="https://www.google-analytics.com/g/collect?en=page_view",
):
    return RequestObservation(
        url=url,
        method="GET",
        category=category,
        phase=phase,
        host="www.google-analytics.com",
        timestamp=10.0,
        resource_type="fetch",
    )


def _finding_ids(findings):
    return {finding.rule_id for finding in findings}


def test_denied_consent_plus_pre_consent_request_is_high_confidence():
    findings = analyze_cmp(
        url="https://example.test",
        detections=(CmpDetection("cookiebot", "Cookiebot", "1", "confirmed"),),
        initial_state=_state(analytics=False),
        after_action_state=None,
        after_reload_state=None,
        lifecycle=ConsentLifecycle(),
        requests=(_request(),),
        cookies=(),
    )
    finding = next(
        item for item in findings if item.rule_id == "cmp.tracking_before_consent.analytics"
    )
    assert finding.severity == "high"
    assert finding.confidence == "high-confidence"


def test_unknown_consent_state_makes_pre_consent_request_a_lead_not_a_verdict():
    findings = analyze_cmp(
        url="https://example.test",
        detections=(CmpDetection("cookiebot", "Cookiebot", "1", "confirmed"),),
        initial_state=_state(analytics=None),
        after_action_state=None,
        after_reload_state=None,
        lifecycle=ConsentLifecycle(),
        requests=(_request(),),
        cookies=(),
    )
    finding = next(
        item for item in findings if item.rule_id == "cmp.tracking_before_consent.analytics"
    )
    assert finding.severity == "medium"
    assert finding.confidence == "suspected"


def test_tracking_after_explicit_reject_is_critical():
    findings = analyze_cmp(
        url="https://example.test",
        detections=(CmpDetection("cookiebot", "Cookiebot", "1", "confirmed"),),
        initial_state=_state(analytics=False),
        after_action_state=_state(analytics=False),
        after_reload_state=None,
        lifecycle=ConsentLifecycle(requested_action="reject", authorized=True, performed=True),
        requests=(_request(phase="after_action"),),
        cookies=(),
    )
    finding = next(item for item in findings if item.rule_id == "cmp.tracking_after_reject")
    assert finding.severity == "critical"
    assert finding.confidence == "high-confidence"


def test_missing_consent_control_is_reported_without_pretending_action_happened():
    findings = analyze_cmp(
        url="https://example.test",
        detections=(CmpDetection("cookiebot", "Cookiebot", "1", "confirmed"),),
        initial_state=_state(),
        after_action_state=None,
        after_reload_state=None,
        lifecycle=ConsentLifecycle(
            requested_action="accept",
            authorized=True,
            performed=False,
            failure_reason="no_selector_available",
        ),
        requests=(),
        cookies=(),
    )
    finding = next(item for item in findings if item.rule_id == "cmp.consent_control_unavailable")
    assert finding.severity == "medium"
    assert finding.confidence == "confirmed"


def test_consent_change_after_reload_is_reported_as_not_persisted():
    findings = analyze_cmp(
        url="https://example.test",
        detections=(CmpDetection("cookiebot", "Cookiebot", "1", "confirmed"),),
        initial_state=_state(analytics=False),
        after_action_state=_state(analytics=True),
        after_reload_state=_state(analytics=False),
        lifecycle=ConsentLifecycle(
            requested_action="accept", authorized=True, performed=True, reloaded=True
        ),
        requests=(),
        cookies=(),
    )
    assert "cmp.consent_not_persisted" in _finding_ids(findings)


def test_findings_are_deduped_by_stable_id_and_keep_evidence():
    first = CmpDetection("cookiebot", "Cookiebot", "1", "confirmed")
    state = _state(analytics=False)
    request = _request()
    findings_a = analyze_cmp(
        url="https://example.test",
        detections=(first,),
        initial_state=state,
        after_action_state=None,
        after_reload_state=None,
        lifecycle=ConsentLifecycle(),
        requests=(request,),
        cookies=(),
    )
    findings_b = analyze_cmp(
        url="https://example.test",
        detections=(first,),
        initial_state=state,
        after_action_state=None,
        after_reload_state=None,
        lifecycle=ConsentLifecycle(),
        requests=(
            request,
            _request(url="https://www.google-analytics.com/g/collect?en=scroll"),
        ),
        cookies=(),
    )
    assert len(findings_b) <= len(findings_a) + 1
    combined = dedupe_findings(tuple(findings_a) + tuple(findings_b))
    assert len(combined) == len({item.finding_id for item in combined})


def test_script_assets_are_not_misreported_as_collection_requests():
    assert _classify_request("https://www.google-analytics.com/analytics.js", "script") == "other"
    assert _classify_request("https://connect.facebook.net/en_US/fbevents.js", "script") == "other"
    assert (
        _classify_request("https://www.google-analytics.com/g/collect?en=page_view", "fetch")
        == "analytics"
    )
    assert _classify_request("https://www.facebook.com/tr?id=1", "image") == "advertising"


def test_urls_are_sanitized_before_evidence_serialization():
    assert (
        sanitize_url("https://example.test/path?token=secret&email=x#frag")
        == "https://example.test/path"
    )


def test_unknown_cmp_cookie_is_reported_as_an_observation_not_a_violation():
    findings = analyze_cmp(
        url="https://example.test",
        detections=(),
        initial_state=ConsentState(),
        after_action_state=None,
        after_reload_state=None,
        lifecycle=ConsentLifecycle(),
        requests=(),
        cookies=(CookieMetadata(name="OptanonConsent", domain="example.test"),),
    )
    finding = next(
        item for item in findings if item.rule_id == "cmp.consent_cookie_without_detection"
    )
    assert finding.severity == "informational"
    assert finding.confidence == "suspected"


def test_schema_is_valid_json_and_has_no_raw_cookie_value_field():
    schema = json.loads(_SCHEMA_PATH.read_text())
    assert schema["properties"]["schema_version"]["const"] == 1
    cookie_props = schema["properties"]["cookies"]["items"]["properties"]
    assert "value" not in cookie_props


def test_report_rendering_and_json_shape_are_stable(cmp_fixture_server):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.2)).run(
        f"{cmp_fixture_server}/cookiebot.html"
    )
    payload = report.to_dict()
    assert payload["schema_version"] == 1
    assert payload["summary"]["detected_cmp_count"] >= 1
    assert payload["detections"][0]["adapter_id"] == "cookiebot"
    assert payload["consent"]["initial"]["categories"]["analytics"] is False
    assert "stamp-fixture" not in json.dumps(payload)
    assert "cookiebot" in render_cmp_audit_report(report).lower()
    assert "cmp.tracking_before_consent.analytics" in {
        finding["rule_id"] for finding in payload["findings"]
    }


def test_consent_action_requires_explicit_authorization_before_any_browser_launch():
    with pytest.raises(CmpAuditAuthorizationError):
        CmpAuditRunner().run("http://127.0.0.1:9/never-loaded", consent_action="accept")


def test_authorized_accept_updates_state_without_fabricating_post_reject_tracking(
    cmp_fixture_server,
):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.2)).run(
        f"{cmp_fixture_server}/cookiebot.html",
        consent_action="accept",
        authorize_consent_interaction=True,
    )
    assert report.lifecycle.performed is True
    assert report.consent_after_action is not None
    assert report.consent_after_action.category("analytics") is True
    assert "cmp.tracking_after_reject" not in _finding_ids(report.findings)


def test_authorized_reject_detects_post_reject_collection(cmp_fixture_server):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.2)).run(
        f"{cmp_fixture_server}/cookiebot.html",
        consent_action="reject",
        authorize_consent_interaction=True,
    )
    assert report.lifecycle.performed is True
    assert report.consent_after_action is not None
    assert report.consent_after_action.category("analytics") is False
    assert "cmp.tracking_after_reject" in _finding_ids(report.findings)


def test_reload_persistence_is_checked_not_assumed(cmp_fixture_server):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.2, reload_after_consent=True)).run(
        f"{cmp_fixture_server}/cookiebot.html",
        consent_action="accept",
        authorize_consent_interaction=True,
    )
    assert report.lifecycle.reloaded is True
    assert report.consent_after_reload is not None
    assert report.consent_after_reload.category("analytics") is False
    assert "cmp.consent_not_persisted" in _finding_ids(report.findings)


def test_no_cmp_fixture_is_reported_as_limited_evidence_not_a_violation(
    cmp_fixture_server,
):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.1)).run(
        f"{cmp_fixture_server}/no_cmp.html"
    )
    assert report.detections == ()
    assert "cmp.no_supported_cmp_detected" in _finding_ids(report.findings)
    assert any("Absence of detection is not evidence" in item for item in report.limitations)


def _custom_adapter_payload(adapter_id="acme-consent"):
    return {
        "adapter_id": adapter_id,
        "vendor": "Acme Consent",
        "script_markers": ["cdn.acme.test/consent.js"],
        "global_names": ["AcmeConsent"],
        "cookie_names": ["acme_consent"],
        "accept_selectors": ["#acme-accept-all"],
        "reject_selectors": ["#acme-reject-all"],
    }


def _write_adapter_file(path: Path, adapters):
    path.write_text(json.dumps({"schema_version": 1, "adapters": adapters}), encoding="utf-8")
    return path


def test_declarative_custom_adapter_is_loaded_and_detected(tmp_path):
    path = _write_adapter_file(tmp_path / "adapter.json", [_custom_adapter_payload()])
    adapters = load_adapter_file(path)
    detections = detect_adapters(
        _signals(
            "<html><body>custom</body></html>",
            cookies=("acme_consent",),
            globals_present=("AcmeConsent",),
        ),
        adapters=adapters,
    )
    custom = next(item for item in detections if item.adapter_id == "acme-consent")
    assert custom.confidence == "confirmed"
    assert custom.accept_selectors == ("#acme-accept-all",)
    assert "consent_controls" in custom.capabilities


def test_custom_adapter_file_cannot_shadow_builtin_ids(tmp_path):
    path = _write_adapter_file(tmp_path / "adapter.json", [_custom_adapter_payload("cookiebot")])
    with pytest.raises(AdapterFileError, match="reserved or already loaded"):
        load_adapter_file(path)


def test_custom_adapter_file_rejects_unknown_fields_and_missing_signatures(tmp_path):
    unknown = _custom_adapter_payload()
    unknown["read_consent_js"] = "return true"
    path = _write_adapter_file(tmp_path / "unknown.json", [unknown])
    with pytest.raises(AdapterFileError, match="unsupported key"):
        load_adapter_file(path)

    no_signature = {"adapter_id": "empty-adapter", "vendor": "Empty"}
    path = _write_adapter_file(tmp_path / "empty.json", [no_signature])
    with pytest.raises(AdapterFileError, match="detection signature"):
        load_adapter_file(path)


def test_duplicate_custom_adapters_across_files_are_rejected(tmp_path):
    first = _write_adapter_file(tmp_path / "first.json", [_custom_adapter_payload()])
    second = _write_adapter_file(tmp_path / "second.json", [_custom_adapter_payload()])
    with pytest.raises(AdapterFileError, match="reserved or already loaded"):
        load_adapter_files((first, second))


def test_didomi_reader_normalizes_purpose_and_vendor_ids():
    payload = {
        "consent_string": "DIDOMI-SECRET",
        "purposes": {
            "global": {
                "enabled": ["analytics-purpose", "ads-purpose"],
                "disabled": ["personalization-purpose"],
            }
        },
        "vendors": {"global": {"enabled": ["google-analytics"], "disabled": ["ad-vendor"]}},
    }
    state = DidomiAdapter().read_consent(_FakeSession(payload), timestamp=7.0)
    assert state is not None
    assert state.sources == ("didomi_state",)
    assert state.vendor_state["api"] == "didomi"
    assert state.vendor_state["purposes_enabled"] == [
        "analytics-purpose",
        "ads-purpose",
    ]
    assert state.vendor_state["vendors_disabled"] == ["ad-vendor"]
    assert state.categories["analytics"] is None
    assert state.categories["necessary"] is True
    assert "DIDOMI-SECRET" not in json.dumps(state.to_dict())


def test_onetrust_reader_keeps_active_groups_without_mapping_categories():
    state = OneTrustAdapter().read_consent(_FakeSession(",C0001, C0002,C0004,"), timestamp=8.0)
    assert state is not None
    assert state.sources == ("onetrust_groups",)
    assert state.vendor_state == {
        "api": "onetrust",
        "groups_enabled": ["C0001", "C0002", "C0004"],
    }
    assert state.categories["necessary"] is True
    assert state.categories["analytics"] is None
    assert state.confidence == "confirmed"


def test_onetrust_reader_ignores_missing_or_empty_groups():
    adapter = OneTrustAdapter()
    assert adapter.read_consent(_FakeSession(None)) is None
    assert adapter.read_consent(_FakeSession(" , , ")) is None
    assert adapter.read_consent(_FakeSession([])) is None


def test_onetrust_reader_accepts_group_array_shape():
    state = OneTrustAdapter().read_consent(_FakeSession(["C0001", "C0002"]))
    assert state is not None
    assert state.vendor_state["groups_enabled"] == ["C0001", "C0002"]


def test_browser_reads_onetrust_active_groups(cmp_fixture_server):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.1)).run(
        f"{cmp_fixture_server}/onetrust.html"
    )
    assert report.detections[0].adapter_id == "onetrust"
    assert report.detections[0].confidence == "confirmed"
    assert report.consent_initial.vendor_state["groups_enabled"] == [
        "C0001",
        "C0002",
        "C0004",
    ]
    assert report.consent_initial.categories["analytics"] is None
    assert "groups_enabled=3" in render_cmp_audit_report(report)


def test_browser_reads_didomi_state_without_consent_string(cmp_fixture_server):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.1)).run(
        f"{cmp_fixture_server}/didomi.html"
    )
    assert report.detections[0].adapter_id == "didomi"
    assert report.detections[0].confidence == "confirmed"
    assert report.consent_initial.vendor_state["purposes_enabled"] == [
        "analytics-purpose",
        "ads-purpose",
    ]
    assert report.consent_initial.vendor_state["vendors_enabled"] == ["google-analytics"]
    assert "DIDOMI-SECRET-STRING" not in json.dumps(report.to_dict())


def test_tcf_purpose_mapping_is_conservative_and_gdpr_aware():
    granted = {str(index): True for index in range(1, 12)}
    categories = tcf_categories_from_purposes(granted, gdpr_applies=True)
    assert categories["necessary"] is True
    assert categories["advertising"] is True
    assert categories["analytics"] is True
    assert categories["preferences"] is True

    mixed = {"2": True, "3": False, "4": True, "7": True}
    assert tcf_categories_from_purposes(mixed)["advertising"] is None
    not_applicable = tcf_categories_from_purposes(granted, gdpr_applies=False)
    assert not_applicable["analytics"] is None
    assert not_applicable["advertising"] is None


def test_tcf_reader_normalizes_data_without_the_tc_string():
    payload = {
        "gdprApplies": True,
        "eventStatus": "tcloaded",
        "cmpStatus": "loaded",
        "tcString": "SECRET-TCF",
        "purpose": {
            "consents": {
                "2": True,
                "3": True,
                "4": True,
                "7": True,
                "8": False,
                "9": False,
                "10": False,
                "5": True,
                "6": True,
                "11": True,
            }
        },
        "legitimateInterests": {"consents": {"2": False}},
        "specialFeatures": {"optins": {"1": True}},
    }
    state = read_tcf_consent(_FakeSession(payload), timestamp=12.5)
    assert state is not None
    assert state.categories["advertising"] is True
    assert state.categories["analytics"] is False
    assert state.tcf["gdpr_applies"] is True
    assert state.tcf["purpose_consents"]["2"] is True
    assert "tcString" not in json.dumps(state.to_dict())
    assert "SECRET-TCF" not in json.dumps(state.to_dict())


def test_gpp_reader_normalizes_metadata_without_the_gpp_string():
    payload = {
        "gppVersion": "1.1",
        "cmpStatus": "loaded",
        "signalStatus": "ready",
        "gppString": "SECRET-GPP",
        "applicableSections": [7, 8],
        "parsedSections": {"7": {"secret": "SECTION-SECRET"}},
    }
    state = read_gpp_consent(_FakeSession(payload), timestamp=12.5)
    assert state is not None
    assert state.gpp["applicable_sections"] == ["7", "8"]
    assert state.gpp["parsed_section_ids"] == ["7"]
    assert state.categories["necessary"] is True
    assert state.categories["advertising"] is None
    serialized = json.dumps(state.to_dict())
    assert "SECRET-GPP" not in serialized
    assert "SECTION-SECRET" not in serialized


def test_browser_collects_tcf_and_gpp_without_serializing_consent_strings(
    cmp_fixture_server,
):
    report = CmpAuditRunner(CmpAuditOptions(wait_seconds=0.1)).run(
        f"{cmp_fixture_server}/tcf_gpp.html"
    )
    assert report.consent_initial.tcf["gdpr_applies"] is True
    assert report.consent_initial.categories["advertising"] is True
    assert report.consent_initial.categories["analytics"] is False
    assert report.consent_initial.gpp["applicable_sections"] == ["7"]
    serialized = json.dumps(report.to_dict())
    assert "TCF-SECRET-STRING" not in serialized
    assert "GPP-SECRET-STRING" not in serialized
    assert "SECTION-SECRET" not in serialized


def test_runner_accepts_a_custom_adapter_and_explicit_consent_control(tmp_path, cmp_fixture_server):
    path = _write_adapter_file(tmp_path / "adapter.json", [_custom_adapter_payload()])
    adapters = load_adapter_file(path)
    report = CmpAuditRunner(
        CmpAuditOptions(
            wait_seconds=0.1,
            extra_adapters=adapters,
            accept_selectors=("#acme-accept-all",),
        )
    ).run(
        f"{cmp_fixture_server}/custom_cmp.html",
        consent_action="accept",
        authorize_consent_interaction=True,
    )
    assert report.detections[0].adapter_id == "acme-consent"
    assert report.lifecycle.performed is True
    assert report.lifecycle.selector == "#acme-accept-all"


def test_cli_uses_custom_adapter_file(tmp_path, cmp_fixture_server):
    path = _write_adapter_file(tmp_path / "adapter.json", [_custom_adapter_payload()])
    result = CliRunner().invoke(
        main,
        [
            "cmp",
            "audit",
            f"{cmp_fixture_server}/custom_cmp.html",
            "--adapter-file",
            str(path),
            "--wait",
            "0.1",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["detections"][0]["adapter_id"] == "acme-consent"
    assert payload["consent"]["initial"]["sources"] == ["cookie_presence"]


def test_cli_rejects_invalid_adapter_file_without_launching_browser(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 1, "adapters": [{"adapter_id": "x"}]}')
    result = CliRunner().invoke(
        main,
        [
            "cmp",
            "audit",
            "http://127.0.0.1:9/never-loaded",
            "--adapter-file",
            str(path),
        ],
    )
    assert result.exit_code == 2
    assert "vendor" in result.output.lower()


def test_cli_refuses_consent_action_without_authorization():
    result = CliRunner().invoke(
        main,
        [
            "cmp",
            "audit",
            "http://127.0.0.1:9/never-loaded",
            "--consent-action",
            "accept",
        ],
    )
    assert result.exit_code == 2
    assert "explicit authorization" in result.output.lower()


def test_cli_emits_json_report(cmp_fixture_server):
    result = CliRunner().invoke(
        main,
        ["cmp", "audit", f"{cmp_fixture_server}/no_cmp.html", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["mode"] == "browser"
    assert "cookies" in payload
