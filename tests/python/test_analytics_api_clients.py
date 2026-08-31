"""Unit tests for the GTM/GA4 API clients against injected fake `service`
objects -- no real network calls, no real Google credentials needed. Verifies
the request-shaping and response-normalization logic, which is the part of
these clients that's actually testable without a live account.
"""

from pytagmanager.analytics_api.ga4_client import Ga4ApiClient
from pytagmanager.analytics_api.gtm_client import GtmApiClient


class _FakeExecutable:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeGtmService:
    def __init__(self, accounts, containers_by_account, live_version):
        self._accounts = accounts
        self._containers_by_account = containers_by_account
        self._live_version = live_version
        self.requested_live_parent = None

    def accounts(self):
        return self

    def list(self, parent=None):
        if parent is None:
            return _FakeExecutable({"account": self._accounts})
        return _FakeExecutable({"container": self._containers_by_account.get(parent, [])})

    def containers(self):
        return self

    def versions(self):
        return self

    def live(self, parent):
        self.requested_live_parent = parent
        return _FakeExecutable(self._live_version)


def test_find_container_by_public_id():
    service = _FakeGtmService(
        accounts=[{"path": "accounts/1"}],
        containers_by_account={"accounts/1": [{"path": "accounts/1/containers/2", "publicId": "GTM-ABC123"}]},
        live_version={},
    )
    client = GtmApiClient(service)

    container = client.find_container_by_public_id("GTM-ABC123")
    assert container == {"path": "accounts/1/containers/2", "publicId": "GTM-ABC123"}
    assert client.find_container_by_public_id("GTM-NOPE") is None


def test_get_live_container_config_normalizes_trigger_and_tag():
    live_version = {
        "trigger": [
            {
                "triggerId": "1",
                "name": "Add To Cart",
                "type": "CUSTOM_EVENT",
                "customEventFilter": [
                    {
                        "type": "EQUALS",
                        "parameter": [
                            {"type": "template", "key": "arg0", "value": "{{_event}}"},
                            {"type": "template", "key": "arg1", "value": "add_to_cart"},
                        ],
                    }
                ],
            },
            {"triggerId": "2", "name": "All Clicks", "type": "CLICK"},
        ],
        "tag": [
            {
                "tagId": "10",
                "name": "GA4 - Add to Cart",
                "type": "gaawe",
                "firingTriggerId": ["1"],
                "parameter": [{"key": "eventName", "value": "add_to_cart"}],
            }
        ],
    }
    client = GtmApiClient(_FakeGtmService(accounts=[], containers_by_account={}, live_version=live_version))

    config = client.get_live_container_config("accounts/1/containers/2")

    triggers = {t.trigger_id: t for t in config["triggers"]}
    assert triggers["1"].event_name == "add_to_cart"
    assert triggers["2"].event_name is None  # CLICK trigger doesn't gate on a literal event name

    tag = config["tags"][0]
    assert tag.name == "GA4 - Add to Cart"
    assert tag.firing_trigger_ids == ["1"]
    assert tag.parameters == {"eventName": "add_to_cart"}


class _FakeGa4AdminService:
    def __init__(self, custom_dimensions, conversion_events):
        self._custom_dimensions = custom_dimensions
        self._conversion_events = conversion_events

    def properties(self):
        return self

    def customDimensions(self):
        self._next = "dimensions"
        return self

    def conversionEvents(self):
        self._next = "events"
        return self

    def list(self, parent):
        if self._next == "dimensions":
            return _FakeExecutable({"customDimensions": self._custom_dimensions})
        return _FakeExecutable({"conversionEvents": self._conversion_events})


class _FakeGa4DataService:
    def __init__(self, rows_by_event):
        self._rows_by_event = rows_by_event

    def properties(self):
        return self

    def runRealtimeReport(self, property, body):
        event_name = body["dimensionFilter"]["filter"]["stringFilter"]["value"]
        rows = self._rows_by_event.get(event_name, [])
        return _FakeExecutable({"rows": rows})


def test_ga4_list_custom_dimensions_and_conversion_events():
    admin = _FakeGa4AdminService(
        custom_dimensions=[{"parameterName": "plan_tier", "displayName": "Plan Tier", "scope": "EVENT"}],
        conversion_events=[{"eventName": "purchase"}],
    )
    client = Ga4ApiClient(admin_service=admin, data_service=_FakeGa4DataService({}))

    dimensions = client.list_custom_dimensions("123456")
    assert dimensions[0].parameter_name == "plan_tier"

    events = client.list_conversion_events("123456")
    assert events[0].event_name == "purchase"


def test_ga4_realtime_ingestion_confirmation():
    data = _FakeGa4DataService(
        rows_by_event={"add_to_cart": [{"metricValues": [{"value": "3"}]}], "checkout": [{"metricValues": [{"value": "0"}]}]}
    )
    client = Ga4ApiClient(admin_service=None, data_service=data)

    assert client.was_event_ingested_realtime("123456", "add_to_cart") is True
    assert client.was_event_ingested_realtime("123456", "checkout") is False
    assert client.was_event_ingested_realtime("123456", "never_seen") is False


def test_ga4_realtime_ingestion_returns_none_on_api_error():
    class _BrokenDataService:
        def properties(self):
            raise RuntimeError("API unavailable")

    client = Ga4ApiClient(admin_service=None, data_service=_BrokenDataService())
    assert client.was_event_ingested_realtime("123456", "add_to_cart") is None
