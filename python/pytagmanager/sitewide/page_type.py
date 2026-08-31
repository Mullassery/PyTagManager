"""LLM-backed semantic page-type classification, mirroring
`pytagmanager.intent.ollama_classifier`'s pattern exactly: a locally
running Ollama model (not a hosted API), with a deterministic
URL/content-keyword fallback when Ollama isn't reachable.

`sitewide.templates.detect_templates()` groups pages by URL pattern and DOM
structural fingerprint and labels each group from a URL segment -- a
naming heuristic, not an understanding of what a page is *for* (a
`/deals` page is labeled "Deals" because that's its URL segment, not
because PyTagManager understands ecommerce page semantics). This module is
that semantic layer: given a page's title/headings/CTA text, classify it
into one of a fixed set of page types, optionally used to relabel
templates with something more meaningful than a URL segment.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Protocol, Sequence, runtime_checkable
from urllib.parse import urlparse

from pytagmanager.sitewide.templates import PageTemplate

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:0.5b"

PAGE_TYPES = [
    "Homepage",
    "Product",
    "Category",
    "Search",
    "Article",
    "Landing",
    "Contact",
    "Cart",
    "Checkout",
    "Confirmation",
    "Account",
    "Other",
]


@dataclass(frozen=True)
class PageSummary:
    """A privacy-conscious digest of a page's content -- titles, headings,
    and CTA/link text, never full HTML or form values -- sized to fit a
    small local model's context window."""

    url: str
    title: str
    headings: List[str] = field(default_factory=list)
    cta_texts: List[str] = field(default_factory=list)
    form_count: int = 0


@dataclass(frozen=True)
class PageTypeResult:
    page_type: str  # one of PAGE_TYPES
    confidence: float
    rationale: str


@runtime_checkable
class PageTypeClassifier(Protocol):
    def classify(self, summary: PageSummary) -> PageTypeResult: ...


def summarize_page(graph: Any) -> PageSummary:
    headings = [n.text for n in graph.nodes if n.tag in ("h1", "h2") and n.text][:5]
    cta_texts = [n.text for n in graph.nodes if n.tag in ("a", "button") and n.text][:10]
    form_count = sum(1 for n in graph.nodes if n.tag == "form")
    return PageSummary(
        url=graph.url,
        title=headings[0] if headings else "",
        headings=headings,
        cta_texts=cta_texts,
        form_count=form_count,
    )


# (URL-path substring, page type), checked in order -- first match wins.
_URL_KEYWORD_MAP = [
    ("checkout", "Checkout"),
    ("thank-you", "Confirmation"),
    ("order-confirm", "Confirmation"),
    ("confirmation", "Confirmation"),
    ("cart", "Cart"),
    ("account", "Account"),
    ("profile", "Account"),
    ("login", "Account"),
    ("contact", "Contact"),
    ("search", "Search"),
    ("blog", "Article"),
    ("article", "Article"),
    ("news", "Article"),
    ("product", "Product"),
    ("category", "Category"),
    ("collections", "Category"),
    ("shop", "Category"),
]


class HeuristicPageTypeClassifier:
    """Deterministic fallback: URL-path keyword matching, same spirit as
    `recommend.heuristics`'s keyword-driven CTA classification. Always
    available -- no network call, no external service."""

    def classify(self, summary: PageSummary) -> PageTypeResult:
        path = urlparse(summary.url).path.strip("/").lower()
        if not path:
            return PageTypeResult("Homepage", 0.9, "Root path with no segments.")
        for keyword, page_type in _URL_KEYWORD_MAP:
            if keyword in path:
                return PageTypeResult(page_type, 0.6, f"URL path contains '{keyword}'.")
        if summary.form_count >= 1 and any("contact" in heading.lower() for heading in summary.headings):
            return PageTypeResult("Contact", 0.5, "Page contains a form and a 'contact' heading.")
        return PageTypeResult("Other", 0.3, "No matching URL or content signal.")


class OllamaPageTypeClassifier:
    """`PageTypeClassifier` backed by a local Ollama model. Not "Claude" --
    see `pytagmanager.intent.ollama_classifier`'s module docstring for why
    that distinction is named explicitly rather than glossed over."""

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fallback = HeuristicPageTypeClassifier()

    def is_available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def classify(self, summary: PageSummary) -> PageTypeResult:
        if self.is_available():
            try:
                return self._classify_via_ollama(summary)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError, KeyError):
                pass  # fall through to the deterministic fallback below
        return self._fallback_result(summary)

    def _build_prompt(self, summary: PageSummary) -> str:
        return (
            "You are classifying a webpage's type for a website analytics tool. "
            "Given the page summary below, choose the single best-fitting page type.\n\n"
            f"URL: {summary.url}\n"
            f"Title/first heading: {summary.title!r}\n"
            f"Headings: {summary.headings}\n"
            f"CTA/link text on page: {summary.cta_texts}\n"
            f"Form count: {summary.form_count}\n\n"
            f"Allowed page_type values (choose exactly one): {PAGE_TYPES}\n\n"
            "Respond with ONLY a JSON object of the form: "
            '{"page_type": "<one of the allowed values>", '
            '"confidence": <float between 0 and 1>, '
            '"rationale": "<one short sentence>"}'
        )

    def _classify_via_ollama(self, summary: PageSummary) -> PageTypeResult:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": self._build_prompt(summary),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0},
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        parsed = json.loads(body.get("response", ""))
        page_type = parsed.get("page_type", "Other")
        if page_type not in PAGE_TYPES:
            page_type = "Other"

        confidence = max(0.0, min(float(parsed.get("confidence", 0.5)), 1.0))
        rationale = str(parsed.get("rationale") or "").strip()
        rationale = f"Ollama ({self.model}): {rationale}" if rationale else f"Ollama ({self.model}) classification."

        return PageTypeResult(page_type=page_type, confidence=confidence, rationale=rationale)

    def _fallback_result(self, summary: PageSummary) -> PageTypeResult:
        result = self._fallback.classify(summary)
        return PageTypeResult(
            page_type=result.page_type,
            confidence=result.confidence,
            rationale=f"Ollama unavailable; {result.rationale}",
        )


def assign_semantic_labels(
    templates: Sequence[PageTemplate],
    graphs_by_url: Dict[str, Any],
    classifier: PageTypeClassifier,
    sample_size: int = 3,
) -> List[PageTemplate]:
    """Relabel each template with a majority vote across a sample of its
    pages' classified page types, instead of the URL-segment-derived label
    `detect_templates()` assigns by default. A template with no
    classifiable sample (e.g. no matching graph) keeps its original label
    rather than being relabeled to a guess.
    """
    relabeled = []
    for template in templates:
        votes: Dict[str, int] = {}
        for url in template.page_urls[:sample_size]:
            graph = graphs_by_url.get(url)
            if graph is None:
                continue
            result = classifier.classify(summarize_page(graph))
            votes[result.page_type] = votes.get(result.page_type, 0) + 1
        if votes:
            new_label = max(votes.items(), key=lambda kv: kv[1])[0]
            relabeled.append(replace(template, label=new_label))
        else:
            relabeled.append(template)
    return relabeled
