"""Tests for Phase 1.7's cookie/storage purpose classification
(docs/VISION.md §6): deterministic key-name/evidence-based classification,
plus the Ollama re-ranker's fallback behavior when Ollama isn't running."""

from __future__ import annotations

from pytagmanager.dictionary.build import DictionaryVariable
from pytagmanager.dictionary.purpose import (
    HeuristicPurposeClassifier,
    OllamaPurposeClassifier,
)


def _variable(
    path: str, pages_present=("https://example.com/",), pages_total=1
) -> DictionaryVariable:
    return DictionaryVariable(
        source="cookie",
        path=path,
        value_types=("string",),
        pages_present=pages_present,
        pages_total=pages_total,
        first_observed=1.0,
        last_observed=1.0,
    )


def test_classifies_session_cookie():
    result = HeuristicPurposeClassifier().classify(_variable("PHPSESSID"))
    assert result.purpose == "Session"
    assert result.confidence > 0
    assert any("session" in e.lower() for e in result.evidence)


def test_classifies_advertising_cookie():
    result = HeuristicPurposeClassifier().classify(_variable("_fbp"))
    assert result.purpose == "Advertising"


def test_classifies_consent_cookie():
    result = HeuristicPurposeClassifier().classify(_variable("cookie_consent_status"))
    assert result.purpose == "Consent"


def test_classifies_cart_cookie():
    result = HeuristicPurposeClassifier().classify(_variable("cart_id"))
    assert result.purpose == "Cart"


def test_unrecognized_key_with_no_evidence_is_unknown_with_zero_confidence():
    result = HeuristicPurposeClassifier().classify(_variable("xk392"))
    assert result.purpose == "Unknown"
    assert result.confidence == 0.0
    assert result.evidence == []


def test_persistence_across_pages_is_recorded_as_evidence():
    result = HeuristicPurposeClassifier().classify(
        _variable(
            "customer_id",
            pages_present=("https://example.com/a", "https://example.com/b"),
            pages_total=2,
        )
    )
    assert result.purpose == "Identity"
    assert any("persists across" in e for e in result.evidence)


def test_campaign_url_param_cooccurrence_is_recorded_as_evidence():
    result = HeuristicPurposeClassifier().classify(
        _variable(
            "mystery_id",
            pages_present=("https://example.com/?utm_source=newsletter",),
            pages_total=1,
        )
    )
    assert any("campaign query parameter" in e for e in result.evidence)


def test_ollama_classifier_falls_back_to_heuristic_when_unreachable():
    classifier = OllamaPurposeClassifier(base_url="http://localhost:1")  # nothing listening
    result = classifier.classify(_variable("_fbp"))
    assert result.purpose == "Advertising"
    assert "Ollama unavailable" in result.rationale
