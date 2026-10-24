"""Unit tests for Phase 1.95 item 2's script inventory helper logic (no
browser): first-party comparison and initiator-URL extraction."""

from __future__ import annotations

from pytagmanager.perf.scripts import _initiator_url_from, _is_first_party


def test_is_first_party_same_domain():
    assert _is_first_party("https://shop.example.com/a.js", "https://shop.example.com/") is True


def test_is_first_party_subdomain_counts_as_first_party():
    assert _is_first_party("https://cdn.example.com/a.js", "https://shop.example.com/") is True


def test_is_first_party_different_domain_is_third_party():
    assert (
        _is_first_party("https://connect.facebook.net/a.js", "https://shop.example.com/") is False
    )


def test_is_first_party_empty_hostname_is_false():
    assert _is_first_party("", "https://shop.example.com/") is False


def test_initiator_url_from_script_type_uses_first_stack_frame():
    initiator = {
        "type": "script",
        "stack": {"callFrames": [{"url": "https://shop.example.com/loader.js"}]},
    }
    assert _initiator_url_from(initiator) == "https://shop.example.com/loader.js"


def test_initiator_url_from_parser_type_uses_url_field():
    initiator = {"type": "parser", "url": "https://shop.example.com/index.html"}
    assert _initiator_url_from(initiator) == "https://shop.example.com/index.html"


def test_initiator_url_from_empty_stack_falls_back_to_none():
    initiator = {"type": "script", "stack": {"callFrames": []}}
    assert _initiator_url_from(initiator) is None
