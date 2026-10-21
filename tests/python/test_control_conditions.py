from __future__ import annotations

import pytest

from pytagmanager.control.conditions import (
    evaluate_condition,
    pattern_matches,
    validate_condition,
)
from pytagmanager.control.errors import ValidationError

CONTEXT = {
    "event": {"name": "add_to_cart", "type": "click", "value": 25, "flag": True},
    "page": {"url": "https://example.com/products/1", "path": "/products/1"},
    "data_layer": {"cart": {"id": "c-1", "items": ["a", "b"]}},
    "consent": {"analytics": True, "marketing": False},
    "variables": {"var-1": "value"},
}


@pytest.mark.parametrize(
    ("pattern", "value", "expected"),
    [
        ("*", "anything", True),
        ("page_*", "page_view", True),
        ("page_*", "xpage_view", False),
        ("*_view", "page_view", True),
        ("*view*", "page_viewed", True),
        ("exact", "exact", True),
        ("exact", "exactly", False),
        ("a?c", "abc", True),
        ("a?c", "ac", False),
        ("**", "anything", True),
        ("a*b*c", "axxbyyc", True),
        ("a*b*c", "axxbyy", False),
        ("", "", True),
        ("", "x", False),
    ],
)
def test_glob_matches_pytagshield_semantics(pattern, value, expected):
    assert pattern_matches(pattern, value) is expected


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ({"op": "equals", "path": "event.name", "value": "add_to_cart"}, True),
        ({"op": "equals", "path": "event.flag", "value": 1}, False),
        ({"op": "equals", "path": "event.missing", "value": None}, False),
        ({"op": "contains", "path": "page.url", "value": "/products/"}, True),
        ({"op": "contains", "path": "data_layer.cart.items", "value": "a"}, True),
        ({"op": "starts_with", "path": "page.path", "value": "/checkout"}, False),
        ({"op": "starts_with", "path": "page.path", "value": "/products"}, True),
        ({"op": "matches_glob", "path": "event.name", "value": "add_*"}, True),
        ({"op": "gt", "path": "event.value", "value": 20}, True),
        ({"op": "gte", "path": "event.value", "value": 25}, True),
        ({"op": "lt", "path": "event.value", "value": 25}, False),
        ({"op": "lte", "path": "event.value", "value": 25}, True),
        ({"op": "gt", "path": "event.flag", "value": 0}, False),
        ({"op": "in", "path": "event.name", "value": ["view", "add_to_cart"]}, True),
        ({"op": "in", "path": "event.missing", "value": [None]}, False),
        ({"op": "exists", "path": "event.name"}, True),
        ({"op": "exists", "path": "event.missing"}, False),
        ({"op": "exists", "path": "data_layer.cart.id"}, True),
    ],
)
def test_every_condition_operator(condition, expected):
    assert evaluate_condition(validate_condition(condition), CONTEXT) is expected


def test_logical_precedence_and_nesting():
    condition = validate_condition(
        {
            "op": "all",
            "conditions": [
                {"op": "equals", "path": "event.type", "value": "click"},
                {
                    "op": "any",
                    "conditions": [
                        {"op": "equals", "path": "event.name", "value": "nope"},
                        {"op": "not", "conditions": [{"op": "equals", "path": "consent.marketing", "value": True}]},
                    ],
                },
            ],
        }
    )
    assert evaluate_condition(condition, CONTEXT) is True

    empty_all = validate_condition({"op": "all", "conditions": []})
    empty_any = validate_condition({"op": "any", "conditions": []})
    assert evaluate_condition(empty_all, CONTEXT) is True
    assert evaluate_condition(empty_any, CONTEXT) is False


@pytest.mark.parametrize(
    "condition",
    [
        {},
        {"op": "nope", "path": "event.name", "value": "x"},
        {"op": "equals", "path": "secret.name", "value": "x"},
        {"op": "equals", "path": "event..name", "value": "x"},
        {"op": "equals", "path": "event.name", "value": "x", "extra": 1},
        {"op": "not", "conditions": []},
        {"op": "all", "conditions": "not-a-list"},
        {"op": "starts_with", "path": "event.name", "value": 1},
        {"op": "in", "path": "event.name", "value": "not-a-list"},
    ],
)
def test_malformed_conditions_are_rejected(condition):
    with pytest.raises(ValidationError):
        validate_condition(condition)


def test_condition_depth_node_and_size_limits():
    nested = {"op": "exists", "path": "event.name"}
    for _ in range(40):
        nested = {"op": "not", "conditions": [nested]}
    with pytest.raises(ValidationError):
        validate_condition(nested)

    too_many = {"op": "all", "conditions": [{"op": "exists", "path": "event.name"}] * 513}
    with pytest.raises(ValidationError):
        validate_condition(too_many)

    too_large = {"op": "equals", "path": "event.name", "value": "x" * 70000}
    with pytest.raises(ValidationError):
        validate_condition(too_large)
