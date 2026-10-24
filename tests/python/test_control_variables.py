from __future__ import annotations

from dataclasses import replace

import pytest
from pytagmanager.control.config import Variable
from pytagmanager.control.errors import ValidationError
from pytagmanager.control.expressions import (
    ExpressionError,
    evaluate_expression,
    validate_expression,
)
from pytagmanager.control.variables import VariableResolver

CONTEXT = {
    "event": {"name": "purchase", "value": "42", "token": "secret-event"},
    "page": {
        "url": "https://example.com/cart",
        "path": "/cart",
        "title": "Cart",
        "referrer": "https://search.example/",
    },
    "data_layer": {
        "cart": {"value": "12.5", "items": ["a", "b"]},
        "token": "secret-dl",
    },
    "consent": {"analytics": True},
    "dom": {
        "#price": {"text": "$19.99", "attributes": {"data-currency": "USD"}},
    },
}


def _resolve(*variables: Variable, context=None):
    resolver = VariableResolver(tuple(variables), context or CONTEXT)
    return {item.name: item for item in resolver.resolve_all()}


def test_basic_sources_and_dom_resolution():
    variables = (
        Variable.create(name="page url", type="string", source="page_url"),
        Variable.create(name="path", type="string", source="page_path"),
        Variable.create(name="title", type="string", source="page_title"),
        Variable.create(name="ref", type="string", source="referrer"),
        Variable.create(name="event value", type="string", source="event", source_ref="value"),
        Variable.create(
            name="cart items", type="list", source="data_layer", source_ref="cart.items"
        ),
        Variable.create(name="analytics", type="boolean", source="consent", source_ref="analytics"),
        Variable.create(name="price", type="string", source="dom", source_ref="#price"),
        Variable.create(
            name="currency",
            type="string",
            source="dom",
            source_ref={"selector": "#price", "attribute": "data-currency"},
        ),
        Variable.create(name="constant", type="string", source="static", default="fixed"),
    )
    resolved = _resolve(*variables)
    assert resolved["page url"].value == "https://example.com/cart"
    assert resolved["path"].value == "/cart"
    assert resolved["title"].value == "Cart"
    assert resolved["ref"].value == "https://search.example/"
    assert resolved["event value"].value == "42"
    assert resolved["cart items"].value == ["a", "b"]
    assert resolved["analytics"].value is True
    assert resolved["price"].value == "$19.99"
    assert resolved["currency"].value == "USD"
    assert resolved["constant"].value == "fixed"


def test_missing_default_and_type_errors():
    resolved = _resolve(
        Variable.create(name="missing", type="string", source="event", source_ref="nope"),
        Variable.create(
            name="defaulted",
            type="number",
            source="event",
            source_ref="nope",
            default=7,
        ),
        Variable.create(name="wrong", type="number", source="event", source_ref="value"),
    )
    assert resolved["missing"].status == "missing"
    assert resolved["missing"].value is None
    assert resolved["defaulted"].status == "default"
    assert resolved["defaulted"].value == 7
    assert resolved["wrong"].status == "error"
    assert "not of type number" in resolved["wrong"].error


def test_disabled_and_unknown_variables():
    disabled = Variable.create(
        name="disabled", type="string", source="static", default="x", enabled=False
    )
    resolver = VariableResolver((disabled,), CONTEXT)
    assert resolver.resolve(disabled.variable_id).status == "disabled"
    unknown = resolver.resolve("00000000-0000-4000-8000-000000000000")
    assert unknown.status == "error"
    assert "unknown variable" in unknown.error


def test_computed_expressions_and_dependency_resolution():
    event_value = Variable.create(name="value", type="string", source="event", source_ref="value")
    cart_value = Variable.create(
        name="cart", type="string", source="data_layer", source_ref="cart.value"
    )
    chosen = Variable.create(
        name="chosen",
        type="number",
        source="computed",
        source_ref={
            "op": "to_number",
            "arg": {
                "op": "coalesce",
                "args": [
                    {"op": "variable", "id": event_value.variable_id},
                    {"op": "variable", "id": cart_value.variable_id},
                ],
            },
        },
    )
    label = Variable.create(
        name="label",
        type="string",
        source="computed",
        source_ref={
            "op": "concat",
            "args": [
                {"op": "literal", "value": "price:"},
                {
                    "op": "to_string",
                    "arg": {"op": "variable", "id": chosen.variable_id},
                },
            ],
        },
    )
    resolved = _resolve(event_value, cart_value, chosen, label)
    assert resolved["chosen"].value == 42
    assert resolved["label"].value == "price:42"


def test_expression_operations():
    def resolver(variable_id: str) -> int:
        return 5

    assert evaluate_expression({"op": "literal", "value": {"a": 1}}, resolver) == {"a": 1}
    assert (
        evaluate_expression({"op": "to_string", "arg": {"op": "literal", "value": True}}, resolver)
        == "true"
    )
    assert (
        evaluate_expression(
            {"op": "to_boolean", "arg": {"op": "literal", "value": "TRUE"}}, resolver
        )
        is True
    )
    assert (
        evaluate_expression({"op": "to_boolean", "arg": {"op": "literal", "value": 1}}, resolver)
        is True
    )
    assert evaluate_expression(
        {"op": "json_parse", "arg": {"op": "literal", "value": '{"a": 1}'}}, resolver
    ) == {"a": 1}
    assert (
        evaluate_expression({"op": "length", "arg": {"op": "literal", "value": [1, 2]}}, resolver)
        == 2
    )
    with pytest.raises(ExpressionError):
        evaluate_expression({"op": "to_number", "arg": {"op": "literal", "value": "no"}}, resolver)
    with pytest.raises(ExpressionError):
        evaluate_expression({"op": "json_parse", "arg": {"op": "literal", "value": "{"}}, resolver)


def test_sensitivity_is_explicit_or_inherited_from_dependencies():
    token = Variable.create(name="token", type="string", source="data_layer", source_ref="token")
    computed = Variable.create(
        name="derived",
        type="string",
        source="computed",
        source_ref={
            "op": "concat",
            "args": [
                {"op": "literal", "value": "prefix-"},
                {"op": "variable", "id": token.variable_id},
            ],
        },
    )
    explicit = Variable.create(
        name="explicit",
        type="string",
        source="static",
        default="hidden",
        sensitive=True,
    )
    resolved = _resolve(token, computed, explicit)
    assert resolved["token"].sensitive is True
    assert resolved["token"].redacted_value == "[REDACTED]"
    assert resolved["derived"].sensitive is True
    assert resolved["derived"].redacted_value == "[REDACTED]"
    assert resolved["explicit"].to_trace_dict()["value"] == "[REDACTED]"


def test_computed_cycle_reports_error():
    first = Variable.create(name="first", type="string", source="static", default="a")
    second = Variable.create(
        name="second",
        type="string",
        source="computed",
        source_ref={"op": "variable", "id": first.variable_id},
    )
    first = replace(
        first,
        source="computed",
        source_ref={"op": "variable", "id": second.variable_id},
    )
    resolved = _resolve(first, second)
    assert resolved["first"].status == "error"
    assert resolved["second"].status == "error"


@pytest.mark.parametrize(
    "expression",
    [
        {},
        {"op": "eval"},
        {"op": "literal", "value": 1, "extra": True},
        {"op": "coalesce", "args": []},
        {"op": "to_number"},
        {"op": "variable", "id": "not-an-id"},
    ],
)
def test_expression_validation_rejects_invalid_nodes(expression):
    with pytest.raises(ValidationError):
        validate_expression(expression)


def test_expression_depth_and_size_limits():
    nested = {"op": "literal", "value": 1}
    for _ in range(20):
        nested = {"op": "to_number", "arg": nested}
    with pytest.raises(ValidationError):
        validate_expression(nested)

    too_many = {"op": "concat", "args": [{"op": "literal", "value": "x"}] * 65}
    with pytest.raises(ValidationError):
        validate_expression(too_many)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "x", "type": "number", "source": "static", "default": "nope"},
        {"name": "x", "type": "string", "source": "event", "source_ref": None},
        {"name": "x", "type": "string", "source": "dom", "source_ref": ""},
        {
            "name": "x",
            "type": "string",
            "source": "computed",
            "source_ref": {"op": "eval"},
        },
        {"name": "x", "type": "string", "source": "nope"},
    ],
)
def test_variable_creation_validates_sources_and_types(kwargs):
    with pytest.raises(ValidationError):
        Variable.create(**kwargs)
