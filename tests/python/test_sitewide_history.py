import json

from pytagmanager.sitewide.aggregation import SiteHealthReport, TemplateHealth
from pytagmanager.sitewide.history import HealthHistoryEntry, append_history_entry, detect_regression, load_history
from pytagmanager.sitewide.templates import PageTemplate


def _site_health(overall_score, template_scores):
    template_healths = [
        TemplateHealth(
            template=PageTemplate(template_id=label, label=label, page_urls=["https://example.com"]),
            score=score,
            healthy=1,
            warnings=0,
            critical=0,
            journeys_total=1,
        )
        for label, score in template_scores.items()
    ]
    return SiteHealthReport(
        pages_scanned=1,
        template_healths=template_healths,
        overall_score=overall_score,
        gtm_coverage=None,
        ga4_coverage=None,
        datalayer_coverage=None,
        event_coverage=None,
        duplicate_rate=None,
        consent_ok_rate=None,
        pages_with_js_errors=0,
    )


def test_load_history_returns_empty_list_for_missing_file(tmp_path):
    assert load_history(str(tmp_path / "nope.json")) == []


def test_append_and_load_history_round_trips(tmp_path):
    path = str(tmp_path / "history.json")
    entry = HealthHistoryEntry.from_site_health("https://example.com", _site_health(90, {"Product": 90}))
    append_history_entry(path, entry)

    loaded = load_history(path)
    assert len(loaded) == 1
    assert loaded[0].overall_score == 90
    assert loaded[0].template_scores == {"Product": 90}

    # File is human-readable JSON, per the version_control snapshot convention.
    data = json.loads((tmp_path / "history.json").read_text())
    assert data["format_version"] == 1


def test_append_history_accumulates_entries(tmp_path):
    path = str(tmp_path / "history.json")
    append_history_entry(path, HealthHistoryEntry.from_site_health("https://example.com", _site_health(90, {})))
    append_history_entry(path, HealthHistoryEntry.from_site_health("https://example.com", _site_health(80, {})))

    loaded = load_history(path)
    assert [e.overall_score for e in loaded] == [90, 80]


def test_detect_regression_none_with_no_history():
    latest = HealthHistoryEntry.from_site_health("https://example.com", _site_health(50, {}))
    assert detect_regression([], latest) is None


def test_detect_regression_flags_site_score_drop():
    previous = HealthHistoryEntry.from_site_health("https://example.com", _site_health(90, {"Product": 90}))
    latest = HealthHistoryEntry.from_site_health("https://example.com", _site_health(80, {"Product": 90}))

    regression = detect_regression([previous], latest, threshold=5)
    assert regression is not None
    assert regression.site_score_drop == 10
    assert "Overall tracking health score dropped 10 points" in regression.message


def test_detect_regression_flags_template_score_drop():
    previous = HealthHistoryEntry.from_site_health("https://example.com", _site_health(90, {"Checkout": 90, "Product": 95}))
    latest = HealthHistoryEntry.from_site_health("https://example.com", _site_health(88, {"Checkout": 60, "Product": 95}))

    regression = detect_regression([previous], latest, threshold=5)
    assert regression is not None
    assert regression.template_drops == {"Checkout": 30}
    assert "Checkout template score dropped 30 points" in regression.message


def test_detect_regression_none_below_threshold():
    previous = HealthHistoryEntry.from_site_health("https://example.com", _site_health(90, {"Product": 90}))
    latest = HealthHistoryEntry.from_site_health("https://example.com", _site_health(88, {"Product": 89}))

    assert detect_regression([previous], latest, threshold=5) is None
