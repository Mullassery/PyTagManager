from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pytagmanager.control.errors import ValidationError
from pytagmanager.events import SCHEMA_VERSION
from pytagmanager.ingest import (
    ForwardResult,
    IngestConfig,
    IngestService,
    PyTagShieldClient,
    SQLiteDedupeStore,
    create_server,
    to_pytagshield_event,
    validate_pytagshield_url,
)


def _event(**overrides):
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": "123e4567-e89b-42d3-a456-426614174000",
        "event_name": "add_to_cart",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "source": {
            "platform": "web",
            "sdk_name": "pytagmanager-web",
            "sdk_version": "0.1.0",
        },
        "container_id": "GTM-ABC1234",
        "subject": {"id": "customer-1", "type": "user"},
        "consent": {
            "purposes": {"analytics": True},
            "source": "sdk",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "provenance": "explicit",
        },
        "properties": {"currency": "EUR"},
    }
    event.update(overrides)
    return event


class FakeForwarder:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def forward(self, event):
        self.calls.append(event)
        if self.results:
            return self.results.pop(0)
        return ForwardResult(
            forwarded=True,
            http_status=200,
            status="accepted",
            destinations=("GA4",),
            enqueued=("GA4",),
            matched_routes=("add_to_cart",),
            consent={"analytics": True},
            consent_source="client",
        )


def test_valid_event_is_forwarded_and_duplicate_is_not():
    forwarder = FakeForwarder()
    service = IngestService(IngestConfig(rate_limit_per_minute=100), forwarder=forwarder)
    first = service.ingest_event(_event(), client_ip="203.0.113.10")
    second = service.ingest_event(_event(), client_ip="203.0.113.10")
    assert first.status == "forwarded"
    assert first.accepted is True
    assert first.forward["destinations"] == ["GA4"]
    assert "properties" not in first.to_dict()
    assert second.status == "duplicate"
    assert second.duplicate is True
    assert len(forwarder.calls) == 1


def test_invalid_event_is_rejected_without_forwarding():
    forwarder = FakeForwarder()
    service = IngestService(forwarder=forwarder)
    result = service.ingest_event(_event(event_name="Bad Name"))
    assert result.status == "rejected"
    assert result.accepted is False
    assert result.errors
    assert forwarder.calls == []


def test_container_allowlist_is_enforced():
    forwarder = FakeForwarder()
    service = IngestService(
        IngestConfig(allowed_containers=frozenset({"GTM-OTHER1"})),
        forwarder=forwarder,
    )
    result = service.ingest_event(_event())
    assert result.status == "rejected"
    assert forwarder.calls == []


def test_transient_forward_failure_releases_the_event_for_retry():
    transient = ForwardResult(
        forwarded=False,
        http_status=503,
        status="transient_error",
        transient=True,
        error="upstream unavailable",
    )
    forwarder = FakeForwarder([transient])
    service = IngestService(forwarder=forwarder)
    first = service.ingest_event(_event())
    second = service.ingest_event(_event())
    assert first.status == "transient_error"
    assert first.retryable is True
    assert second.status == "forwarded"
    assert len(forwarder.calls) == 2


def test_permanent_py_tag_shield_rejection_is_not_retried():
    rejected = ForwardResult(
        forwarded=False,
        http_status=422,
        status="rejected",
        error="invalid event",
    )
    forwarder = FakeForwarder([rejected])
    service = IngestService(forwarder=forwarder)
    first = service.ingest_event(_event())
    second = service.ingest_event(_event())
    assert first.status == "rejected"
    assert second.status == "duplicate"
    assert len(forwarder.calls) == 1


def test_no_forwarder_accepts_without_claiming_delivery():
    service = IngestService()
    result = service.ingest_event(_event())
    assert result.status == "accepted"
    assert result.forwarded is False
    assert result.accepted is True


def test_rate_limit_rejects_before_parsing_and_does_not_forward():
    forwarder = FakeForwarder()
    service = IngestService(IngestConfig(rate_limit_per_minute=1), forwarder=forwarder)
    assert service.ingest_event(_event(), client_ip="198.51.100.4").status == "forwarded"
    limited = service.ingest_event(_event(), client_ip="198.51.100.4")
    assert limited.status == "rate_limited"
    assert limited.retryable is True
    assert len(forwarder.calls) == 1


def test_batch_mixed_validity_preserves_order_and_reports_rejections():
    forwarder = FakeForwarder()
    service = IngestService(forwarder=forwarder)
    raw = {
        "schema_version": SCHEMA_VERSION,
        "events": [
            _event(event_id="123e4567-e89b-42d3-a456-426614174001"),
            _event(event_id="123e4567-e89b-42d3-a456-426614174002", event_name="bad name"),
            _event(event_id="123e4567-e89b-42d3-a456-426614174003", event_name="purchase"),
        ],
    }
    result = service.ingest_batch(raw)
    assert result["status"] == "partial"
    assert [item["event_id"] for item in result["results"]] == [
        "123e4567-e89b-42d3-a456-426614174001",
        None,
        "123e4567-e89b-42d3-a456-426614174003",
    ]
    assert [item["status"] for item in result["results"]] == [
        "forwarded",
        "rejected",
        "forwarded",
    ]
    assert len(forwarder.calls) == 2


def test_pytagshield_mapping_uses_documented_shape():
    event = _event()
    mapped = to_pytagshield_event(event)
    assert mapped["event"] == "add_to_cart"
    assert mapped["distinct_id"] == "customer-1"
    assert isinstance(mapped["timestamp"], int)
    assert mapped["consent"] == {"analytics": True}
    assert mapped["properties"] == {"currency": "EUR"}
    assert "event_id" not in mapped


def test_mapped_event_is_accepted_by_pytagshield_when_available():
    pytest.importorskip("pytagshield")
    import pytagshield

    config = {
        "consent": {"purposes": ["analytics"], "default_policy": "deny"},
        "minimization": {"pseudonymize_salt": "x" * 24},
        "destinations": [{"name": "log", "type": "log", "purpose": "analytics"}],
        "routes": [
            {
                "name": "cart",
                "match": {"events": ["add_to_cart"]},
                "destinations": ["log"],
            }
        ],
    }
    pipeline = pytagshield.Pipeline(pytagshield.Config.from_yaml(json.dumps(config)))
    result = pipeline.process(to_pytagshield_event(_event()))
    assert result["routing"]["destinations"] == ["log"]
    assert result["event"]["distinct_id"].startswith("sha256:")

    anonymous = _event(event_id="123e4567-e89b-42d3-a456-426614174009")
    anonymous.pop("subject")
    anonymous_result = pipeline.process(to_pytagshield_event(anonymous))
    assert anonymous_result["event"]["distinct_id"].startswith("sha256:")


def test_pytagshield_url_requires_https_or_explicit_private_network():
    with pytest.raises(ValidationError):
        validate_pytagshield_url("http://127.0.0.1:8099")
    assert (
        validate_pytagshield_url("http://127.0.0.1:8099", allow_private_networks=True)
        == "http://127.0.0.1:8099"
    )
    with pytest.raises(ValidationError):
        validate_pytagshield_url("https://127.0.0.1:8099")


@contextmanager
def _pytagshield_response(payload, *, status=202):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield PyTagShieldClient(
            f"http://127.0.0.1:{server.server_port}",
            allow_private_networks=True,
        )
    finally:
        server.shutdown()
        server.server_close()


def test_pytagshield_rejected_outcome_is_not_reported_as_forwarded():
    with _pytagshield_response(
        {
            "event_id": "shield-event",
            "status": "rejected",
            "destinations": ["GA4"],
            "enqueued": [],
            "rejected": [{"destination": "GA4", "reason": "queue_full"}],
        }
    ) as client:
        forwarded = client.forward(_event())
        service = IngestService(forwarder=client)
        ingested = service.ingest_event(_event())

    assert forwarded.forwarded is False
    assert forwarded.status == "rejected"
    assert ingested.status == "rejected"
    assert ingested.accepted is False


def test_pytagshield_unexpected_status_fails_closed():
    with _pytagshield_response({"status": "mystery"}) as client:
        result = client.forward(_event())
    assert result.forwarded is False
    assert result.status == "rejected"
    assert result.error == "PyTagShield returned an unexpected ingest status"


def test_pytagshield_backpressure_is_transient():
    with _pytagshield_response({"status": "backpressure"}) as client:
        result = client.forward(_event())
    assert result.forwarded is False
    assert result.transient is True
    assert result.status == "backpressure"


def test_pytagshield_anonymous_events_get_distinct_fallbacks():
    first = _event(event_id="123e4567-e89b-42d3-a456-426614174001")
    second = _event(event_id="123e4567-e89b-42d3-a456-426614174002")
    first.pop("subject")
    second.pop("subject")
    assert to_pytagshield_event(first)["distinct_id"] == "anon:123e4567-e89b-42d3-a456-426614174001"
    assert to_pytagshield_event(first)["distinct_id"] == "anon:123e4567-e89b-42d3-a456-426614174001"
    assert (
        to_pytagshield_event(second)["distinct_id"] == "anon:123e4567-e89b-42d3-a456-426614174002"
    )


def test_pytagshield_client_sends_mapped_event_and_auth(monkeypatch):
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received["path"] = self.path
            received["auth"] = self.headers.get("Authorization")
            received["event_id_header"] = self.headers.get("x-pytagmanager-event-id")
            received["body"] = json.loads(self.rfile.read(length))
            body = json.dumps(
                {
                    "event_id": "shield-event",
                    "status": "accepted",
                    "destinations": ["GA4"],
                    "enqueued": ["GA4"],
                    "consent": {"analytics": True},
                    "consent_source": "client",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("PYTAGSHIELD_TEST_TOKEN", "test-token")
    try:
        client = PyTagShieldClient(
            f"http://127.0.0.1:{server.server_port}",
            token_ref="env:PYTAGSHIELD_TEST_TOKEN",
            allow_private_networks=True,
        )
        result = client.forward(_event())
    finally:
        server.shutdown()
        server.server_close()
    assert result.forwarded is True
    assert result.destinations == ("GA4",)
    assert received["path"] == "/api/v1/event"
    assert received["auth"] == "Bearer test-token"
    assert received["event_id_header"] == "123e4567-e89b-42d3-a456-426614174000"
    assert received["body"]["event"] == "add_to_cart"
    assert received["body"]["distinct_id"] == "customer-1"


@pytest.fixture
def http_endpoint():
    forwarder = FakeForwarder()
    service = IngestService(IngestConfig(rate_limit_per_minute=1000), forwarder=forwarder)
    server = create_server(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, forwarder
    finally:
        server.shutdown()
        server.server_close()


def _request(server, method, path, payload=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    body = None
    merged = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode()
        merged.setdefault("Content-Type", "application/json")
    connection.request(method, path, body=body, headers=merged)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, response.headers, raw


def test_http_health_event_duplicate_and_invalid(http_endpoint):
    server, forwarder = http_endpoint
    status, _, body = _request(server, "GET", "/healthz")
    assert status == 200
    assert json.loads(body)["status"] == "ok"

    status, headers, body = _request(
        server,
        "POST",
        "/api/v1/events",
        _event(),
        headers={"Origin": "https://app.example"},
    )
    assert status == 202
    assert headers["Cache-Control"] == "no-store"
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert json.loads(body)["status"] == "forwarded"
    assert "properties" not in body.decode()

    status, _, body = _request(server, "POST", "/api/v1/events", _event())
    assert status == 202
    assert json.loads(body)["duplicate"] is True

    status, _, body = _request(server, "POST", "/api/v1/events", _event(event_name="Not Valid"))
    assert status == 422
    assert json.loads(body)["status"] == "rejected"
    assert len(forwarder.calls) == 1


def test_http_batch_and_cors_preflight(http_endpoint):
    server, _ = http_endpoint
    raw = {
        "schema_version": SCHEMA_VERSION,
        "events": [
            _event(event_id="123e4567-e89b-42d3-a456-426614174011"),
            _event(event_id="123e4567-e89b-42d3-a456-426614174012", event_name="bad name"),
        ],
    }
    status, _, body = _request(server, "POST", "/api/v1/events", raw)
    assert status == 207
    payload = json.loads(body)
    assert payload["status"] == "partial"
    assert payload["results"][1]["status"] == "rejected"

    status, headers, _ = _request(
        server,
        "OPTIONS",
        "/api/v1/events",
        headers={
            "Origin": "https://app.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_http_rejects_bad_content_type_and_oversized_body(http_endpoint):
    server, _ = http_endpoint
    status, _, _ = _request(
        server,
        "POST",
        "/api/v1/events",
        headers={"Content-Type": "text/plain", "Content-Length": "2"},
    )
    assert status == 415
    status, _, _ = _request(
        server,
        "POST",
        "/api/v1/events",
        {"x": "y" * 70_000},
    )
    assert status == 413


def test_http_api_token_is_optional_but_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("INGEST_TEST_TOKEN", "ingest-secret")
    service = IngestService(
        IngestConfig(api_token_ref="env:INGEST_TEST_TOKEN", rate_limit_per_minute=1000)
    )
    server = create_server(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, _ = _request(server, "POST", "/api/v1/events", _event())
        assert status == 401
        status, _, _ = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(),
            headers={"Authorization": "Bearer ingest-secret"},
        )
        assert status == 202
    finally:
        server.shutdown()
        server.server_close()


def test_http_requires_content_length(http_endpoint):
    server, _ = http_endpoint
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.putrequest("POST", "/api/v1/events")
    connection.putheader("Content-Type", "application/json")
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 411
    response.read()
    connection.close()


def test_batch_rate_limit_charges_once_per_event_and_consumes_tokens():
    forwarder = FakeForwarder()
    service = IngestService(IngestConfig(rate_limit_per_minute=3), forwarder=forwarder)
    first = _batch(("101", "102"))
    assert service.ingest_batch(first, client_ip="203.0.113.20")["status"] == "accepted"
    assert [call["event_id"][-3:] for call in forwarder.calls] == ["101", "102"]

    limited = service.ingest_batch(_batch(("103", "104")), client_ip="203.0.113.20")
    assert limited["status"] == "rate_limited"
    assert len(forwarder.calls) == 2

    one = {
        "schema_version": SCHEMA_VERSION,
        "events": [_event(event_id="123e4567-e89b-42d3-a456-426614174105")],
    }
    assert service.ingest_batch(one, client_ip="203.0.113.20")["status"] == "accepted"
    assert len(forwarder.calls) == 3


def test_batch_larger_than_bucket_is_rejected_without_token_charge():
    service = IngestService(IngestConfig(rate_limit_per_minute=2))
    oversized = {
        "schema_version": SCHEMA_VERSION,
        "events": [_event(event_id=f"123e4567-e89b-42d3-a456-{index:012d}") for index in range(3)],
    }
    limited = service.ingest_batch(oversized, client_ip="203.0.113.21")
    assert limited["status"] == "rate_limited"
    exact = {
        "schema_version": SCHEMA_VERSION,
        "events": [
            _event(event_id="123e4567-e89b-42d3-a456-426614174201"),
            _event(event_id="123e4567-e89b-42d3-a456-426614174202"),
        ],
    }
    assert service.ingest_batch(exact, client_ip="203.0.113.21")["status"] == "accepted"


def _batch(suffixes):
    return {
        "schema_version": SCHEMA_VERSION,
        "events": [
            _event(event_id=f"123e4567-e89b-42d3-a456-{suffix:0>12}") for suffix in suffixes
        ],
    }


def _serve(service):
    server = create_server(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_trusted_proxy_header_controls_rate_limit_identity():
    forwarder = FakeForwarder()
    service = IngestService(
        IngestConfig(
            rate_limit_per_minute=1,
            trusted_proxy_cidrs=("127.0.0.1/32",),
        ),
        forwarder=forwarder,
    )
    server = _serve(service)
    try:
        first = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174301"),
            headers={"X-Forwarded-For": "203.0.113.30"},
        )
        assert first[0] == 202
        same_client = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174302"),
            headers={"X-Forwarded-For": "203.0.113.30"},
        )
        assert same_client[0] == 429
        other_client = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174303"),
            headers={"X-Forwarded-For": "203.0.113.31"},
        )
        assert other_client[0] == 202
    finally:
        server.shutdown()
        server.server_close()
    assert len(forwarder.calls) == 2


def test_forwarded_header_is_ignored_from_untrusted_peer():
    service = IngestService(IngestConfig(rate_limit_per_minute=1))
    server = _serve(service)
    try:
        first = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174311"),
            headers={"X-Forwarded-For": "203.0.113.40"},
        )
        assert first[0] == 202
        spoofed = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174312"),
            headers={"X-Forwarded-For": "203.0.113.41"},
        )
        assert spoofed[0] == 429
    finally:
        server.shutdown()
        server.server_close()


def test_trusted_proxy_chain_uses_rightmost_untrusted_address():
    service = IngestService(
        IngestConfig(
            rate_limit_per_minute=1,
            trusted_proxy_cidrs=("127.0.0.1/32", "10.0.0.5/32"),
        )
    )
    server = _serve(service)
    try:
        first = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174321"),
            headers={"X-Forwarded-For": "203.0.113.50, 10.0.0.5"},
        )
        assert first[0] == 202
        same_client = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174322"),
            headers={"X-Forwarded-For": "203.0.113.50, 10.0.0.5"},
        )
        assert same_client[0] == 429
        other_client = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174323"),
            headers={"X-Forwarded-For": "203.0.113.51, 10.0.0.5"},
        )
        assert other_client[0] == 202
    finally:
        server.shutdown()
        server.server_close()


def test_malformed_forwarded_header_falls_back_to_peer():
    service = IngestService(
        IngestConfig(
            rate_limit_per_minute=1,
            trusted_proxy_cidrs=("127.0.0.1/32",),
        )
    )
    server = _serve(service)
    try:
        first = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174331"),
            headers={"X-Forwarded-For": "not-an-ip"},
        )
        assert first[0] == 202
        second = _request(
            server,
            "POST",
            "/api/v1/events",
            _event(event_id="123e4567-e89b-42d3-a456-426614174332"),
            headers={"X-Forwarded-For": "also-not-an-ip"},
        )
        assert second[0] == 429
    finally:
        server.shutdown()
        server.server_close()


def test_ingest_config_rejects_invalid_proxy_settings():
    with pytest.raises(ValueError, match="invalid trusted proxy CIDR"):
        IngestConfig(trusted_proxy_cidrs=("not-a-cidr",))
    with pytest.raises(ValueError, match="real IP header"):
        IngestConfig(real_ip_header="Bad Header")


def test_sqlite_dedupe_persists_completed_claims_across_restart(tmp_path):
    database = tmp_path / "dedupe.sqlite3"
    first = SQLiteDedupeStore(str(database), ttl_seconds=3600, capacity=100)
    try:
        assert first.claim("event-1") == "claimed"
        first.complete("event-1")
    finally:
        first.close()

    second = SQLiteDedupeStore(str(database), ttl_seconds=3600, capacity=100)
    try:
        assert second.claim("event-1") == "completed"
        assert second.claim("event-2") == "claimed"
    finally:
        second.close()


def test_sqlite_dedupe_reclaims_expired_inflight_claims(tmp_path):
    now = [1_000.0]
    store = SQLiteDedupeStore(
        tmp_path / "dedupe.sqlite3",
        ttl_seconds=3600,
        capacity=100,
        claim_ttl_seconds=30,
        clock=lambda: now[0],
    )
    try:
        assert store.claim("event-1") == "claimed"
        assert store.claim("event-1") == "inflight"
        now[0] += 31
        assert store.claim("event-1") == "claimed"
    finally:
        store.close()


def test_sqlite_dedupe_expires_completed_claims_and_caps_capacity(tmp_path):
    now = [1_000.0]
    store = SQLiteDedupeStore(
        tmp_path / "dedupe.sqlite3",
        ttl_seconds=100,
        capacity=2,
        clock=lambda: now[0],
    )
    try:
        for index in range(3):
            store.claim(f"event-{index}")
            store.complete(f"event-{index}")
            now[0] += 1
        assert store.count("completed") == 2
        assert store.claim("event-0") == "claimed"
        now[0] += 100
        store.complete("event-3")
        assert store.count("completed") == 1
    finally:
        store.close()


def test_sqlite_dedupe_database_is_private(tmp_path):
    import stat

    database = tmp_path / "dedupe.sqlite3"
    store = SQLiteDedupeStore(str(database), ttl_seconds=3600, capacity=100)
    try:
        store.claim("event-1")
        store.complete("event-1")
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(database) + suffix)
            if sidecar.exists():
                assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    finally:
        store.close()


def test_durable_dedupe_is_shared_across_service_instances(tmp_path):
    database = tmp_path / "dedupe.sqlite3"
    first_forwarder = FakeForwarder()
    first = IngestService(
        IngestConfig(dedupe_store_path=str(database), rate_limit_per_minute=1000),
        forwarder=first_forwarder,
    )
    try:
        assert first.ingest_event(_event()).status == "forwarded"
    finally:
        first.close()

    second_forwarder = FakeForwarder()
    second = IngestService(
        IngestConfig(dedupe_store_path=str(database), rate_limit_per_minute=1000),
        forwarder=second_forwarder,
    )
    try:
        duplicate = second.ingest_event(_event())
        assert duplicate.status == "duplicate"
        assert duplicate.duplicate is True
    finally:
        second.close()
    assert len(first_forwarder.calls) == 1
    assert second_forwarder.calls == []


def test_http_health_reports_durable_dedupe_backend(tmp_path):
    service = IngestService(
        IngestConfig(
            dedupe_store_path=str(tmp_path / "dedupe.sqlite3"),
            rate_limit_per_minute=1000,
        )
    )
    server = create_server(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _request(server, "GET", "/healthz")
        assert status == 200
        assert json.loads(body)["dedupe_backend"] == "sqlite"
    finally:
        server.shutdown()
        server.server_close()
