"""Tests for pytagmanager.sitewide.page_type -- mirrors
test_intent_ollama.py's structure: real-Ollama tests skip gracefully when
Ollama isn't reachable, fallback-path tests always run against a
guaranteed-unreachable port.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from pytagmanager import _core
from pytagmanager.sitewide.page_type import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    PAGE_TYPES,
    HeuristicPageTypeClassifier,
    OllamaPageTypeClassifier,
    PageSummary,
    PageTypeResult,
    assign_semantic_labels,
    summarize_page,
)
from pytagmanager.sitewide.templates import PageTemplate


def _ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{DEFAULT_OLLAMA_BASE_URL}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _graph(html: str, url: str):
    return _core.parse_html(html, url)


# -- summarize_page -----------------------------------------------------


def test_summarize_page_extracts_headings_ctas_and_form_count():
    graph = _graph(
        "<html><body><h1>Wireless Headphones</h1><button>Add to Cart</button>"
        "<a href='/reviews'>Read reviews</a><form></form></body></html>",
        "https://example.com/products/123",
    )
    summary = summarize_page(graph)
    assert summary.title == "Wireless Headphones"
    assert "Wireless Headphones" in summary.headings
    assert "Add to Cart" in summary.cta_texts
    assert "Read reviews" in summary.cta_texts
    assert summary.form_count == 1


# -- HeuristicPageTypeClassifier (always available, no network) --------


@pytest.mark.parametrize(
    "url,expected_type",
    [
        ("https://example.com/", "Homepage"),
        ("https://example.com/checkout", "Checkout"),
        ("https://example.com/cart", "Cart"),
        ("https://example.com/products/wireless-headphones", "Product"),
        ("https://example.com/category/electronics", "Category"),
        ("https://example.com/account/profile", "Account"),
        ("https://example.com/order-confirmation/12345", "Confirmation"),
    ],
)
def test_heuristic_classifier_matches_url_keywords(url, expected_type):
    summary = PageSummary(url=url, title="")
    result = HeuristicPageTypeClassifier().classify(summary)
    assert result.page_type == expected_type
    assert result.page_type in PAGE_TYPES


def test_heuristic_classifier_falls_back_to_other():
    summary = PageSummary(url="https://example.com/xyz-unrelated-page", title="")
    result = HeuristicPageTypeClassifier().classify(summary)
    assert result.page_type == "Other"


# -- OllamaPageTypeClassifier fallback path (always runs) ---------------


def test_ollama_classifier_falls_back_when_unavailable():
    classifier = OllamaPageTypeClassifier(base_url="http://127.0.0.1:1")
    assert classifier.is_available() is False

    result = classifier.classify(PageSummary(url="https://example.com/checkout", title=""))
    assert isinstance(result, PageTypeResult)
    assert result.page_type == "Checkout"
    assert "Ollama unavailable" in result.rationale


def test_is_available_false_for_unreachable_host():
    classifier = OllamaPageTypeClassifier(base_url="http://127.0.0.1:1", timeout=1.0)
    assert classifier.is_available() is False


# -- OllamaPageTypeClassifier real call (skipped if Ollama not running) -


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama is not running on localhost:11434")
def test_classify_returns_real_ollama_response():
    classifier = OllamaPageTypeClassifier(model=DEFAULT_OLLAMA_MODEL)
    summary = PageSummary(
        url="https://example.com/products/123",
        title="Wireless Headphones",
        headings=["Wireless Headphones"],
        cta_texts=["Add to Cart", "Buy Now"],
    )
    result = classifier.classify(summary)

    assert result.page_type in PAGE_TYPES
    assert 0.0 <= result.confidence <= 1.0
    assert "Ollama unavailable" not in result.rationale
    assert DEFAULT_OLLAMA_MODEL in result.rationale


# -- assign_semantic_labels ----------------------------------------------


def test_assign_semantic_labels_relabels_by_majority_vote():
    urls = ["https://example.com/products/1", "https://example.com/products/2"]
    template = PageTemplate(template_id="t1", label="Products", page_urls=urls)
    graphs_by_url = {url: _graph("<html><body><h1>x</h1></body></html>", url) for url in urls}

    relabeled = assign_semantic_labels([template], graphs_by_url, HeuristicPageTypeClassifier())
    assert relabeled[0].label == "Product"
    assert relabeled[0].page_urls == urls  # unaffected


def test_assign_semantic_labels_keeps_original_label_when_no_graph_available():
    template = PageTemplate(template_id="t1", label="Products", page_urls=["https://example.com/products/1"])
    relabeled = assign_semantic_labels([template], {}, HeuristicPageTypeClassifier())
    assert relabeled[0].label == "Products"
