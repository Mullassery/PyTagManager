"""Tests for `pytagmanager.intent.ollama_classifier.OllamaIntentClassifier`,
the real LLM-backed `IntentClassifier` implementation (backed by a locally
running Ollama model, not a hosted API -- see the module docstring for why).

The "real Ollama call" tests are skipped (not failed) when Ollama isn't
reachable on localhost:11434, matching the `_internet_reachable` skip
pattern already used in test_core_ffi.py for environment-dependent tests --
CI has no Ollama installed, so these are opt-in/local-only, while the
fallback-path tests (pointed at a guaranteed-unreachable port) always run
and need no live model.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from pytagmanager import _core
from pytagmanager.intent.base import IntentResult, PageContext
from pytagmanager.intent.ollama_classifier import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    OllamaIntentClassifier,
    _TAXONOMY,
)


def _ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{DEFAULT_OLLAMA_BASE_URL}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _add_to_cart_node():
    graph = _core.parse_html(
        '<html><body><button data-testid="add-to-cart" aria-label="Add to cart">Add to Cart</button></body></html>',
        "https://example.com/product",
    )
    return next(n for n in graph.nodes if n.tag == "button")


def _context():
    return PageContext(url="https://example.com/product", page_title="Widget - Product Page")


# -- real Ollama call (skipped if not reachable) -----------------------------


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama is not running on localhost:11434")
def test_is_available_true_when_ollama_running():
    classifier = OllamaIntentClassifier()
    assert classifier.is_available() is True


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama is not running on localhost:11434")
def test_classify_returns_real_ollama_response_for_add_to_cart_button():
    classifier = OllamaIntentClassifier(model=DEFAULT_OLLAMA_MODEL)
    result = classifier.classify(_add_to_cart_node(), _context())

    assert isinstance(result, IntentResult)
    assert result.business_objective in _TAXONOMY
    assert 0.0 <= result.confidence <= 1.0
    assert result.rationale  # non-empty
    # Real model output, not the deterministic fallback path.
    assert "Ollama unavailable" not in result.rationale
    assert DEFAULT_OLLAMA_MODEL in result.rationale


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama is not running on localhost:11434")
def test_classify_handles_unrelated_element_without_crashing():
    graph = _core.parse_html("<html><body><footer>&copy; 2026 Example Corp</footer></body></html>", "https://example.com")
    footer = graph.nodes[0]
    classifier = OllamaIntentClassifier()
    result = classifier.classify(footer, _context())
    assert isinstance(result, IntentResult)
    assert result.business_objective in _TAXONOMY


# -- fallback path (always runs; points at an unreachable port) -------------


def test_classify_falls_back_to_heuristic_when_ollama_unavailable():
    classifier = OllamaIntentClassifier(base_url="http://127.0.0.1:1")  # nothing listens on port 1
    assert classifier.is_available() is False

    result = classifier.classify(_add_to_cart_node(), _context())

    assert isinstance(result, IntentResult)
    assert result.business_objective == "Purchase Intent"  # deterministic keyword match: "add to cart"
    assert "Ollama unavailable" in result.rationale


def test_classify_fallback_returns_none_objective_for_unmatched_element():
    classifier = OllamaIntentClassifier(base_url="http://127.0.0.1:1")
    graph = _core.parse_html("<html><body><div>just some text</div></body></html>", "https://example.com")
    div = graph.nodes[0]

    result = classifier.classify(div, _context())

    assert result.business_objective == "None"
    assert result.confidence == 0.0
    assert "Ollama unavailable" in result.rationale


def test_is_available_false_for_unreachable_host():
    classifier = OllamaIntentClassifier(base_url="http://127.0.0.1:1", timeout=1.0)
    assert classifier.is_available() is False
