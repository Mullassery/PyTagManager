from __future__ import annotations

from typing import List, Optional, Tuple

from pytagmanager._core import SemanticGraph, SemanticNode
from pytagmanager.recommend.models import TrackingRecommendation

# (keyword, business_objective, event_category), checked in order -- first
# match wins. Order matters: more specific phrases are listed before the
# generic terms they contain (e.g. "sign up" before a bare "sign").
_CTA_KEYWORDS: List[Tuple[str, str, str]] = [
    ("add to cart", "Purchase Intent", "ecommerce"),
    ("buy now", "Purchase Intent", "ecommerce"),
    ("checkout", "Purchase Intent", "ecommerce"),
    ("free trial", "Trial Signup", "conversion"),
    ("start trial", "Trial Signup", "conversion"),
    ("subscribe", "Subscription", "conversion"),
    ("newsletter", "Lead Generation", "conversion"),
    ("sign up", "Lead Generation", "conversion"),
    ("sign in", "Authentication", "account"),
    ("log in", "Authentication", "account"),
    ("login", "Authentication", "account"),
    ("register", "Lead Generation", "conversion"),
    ("book a demo", "Lead Generation", "conversion"),
    ("book demo", "Lead Generation", "conversion"),
    ("request a quote", "Lead Generation", "conversion"),
    ("get a quote", "Lead Generation", "conversion"),
    ("contact us", "Lead Generation", "conversion"),
    ("contact", "Lead Generation", "conversion"),
    ("download", "Content Engagement", "engagement"),
    ("get started", "Lead Generation", "conversion"),
    ("learn more", "Content Engagement", "engagement"),
    ("search", "Search", "engagement"),
]

_CTA_TAGS = {"a", "button"}


def _classify(node: SemanticNode) -> Optional[Tuple[str, str, str, List[str]]]:
    """Return (matched_keyword, business_objective, event_category, signals)
    for the first keyword that matches any text/attribute source on `node`,
    or None if nothing matched."""
    haystacks = {
        "text": (node.text or "").lower(),
        "class": " ".join(node.classes).lower(),
        "id": (node.attributes.get("id") or "").lower(),
        "aria_label": (node.aria_label or "").lower(),
    }
    for keyword, objective, category in _CTA_KEYWORDS:
        signals = [f"{source} contains '{keyword}'" for source, value in haystacks.items() if keyword in value]
        if signals:
            return keyword, objective, category, signals
    return None


def classify_node_keywords(node: SemanticNode) -> Optional[Tuple[str, str, str, List[str]]]:
    """Public wrapper around the deterministic keyword classifier used by
    `recommend_for_graph`. Exposed so other callers needing a
    single-element (rather than whole-graph) deterministic classification
    can reuse it instead of reimplementing keyword matching -- notably
    `pytagmanager.intent.ollama_classifier.OllamaIntentClassifier`, which
    falls back to this when the local Ollama model is unavailable.

    Returns `(matched_keyword, business_objective, event_category, signals)`
    or `None` if no CTA keyword matched.
    """
    return _classify(node)


def _selector_fallbacks(node: SemanticNode) -> List[str]:
    fallbacks = []
    if node.stable_selector:
        fallbacks.append(node.stable_selector)
    fallbacks.append(node.css_selector)
    fallbacks.append(node.xpath)
    return fallbacks


def _confidence(node: SemanticNode, matched_signal_count: int) -> float:
    score = 0.3  # base: at least one signal matched
    score += min(matched_signal_count, 3) * 0.15
    if node.stable_selector:
        score += 0.1
    if node.aria_label:
        score += 0.1
    return round(min(score, 0.98), 2)


def _event_name(objective: str) -> str:
    return objective.lower().replace(" ", "_")


def recommend_for_graph(graph: SemanticGraph) -> List[TrackingRecommendation]:
    """Deterministic, rule-based tracking recommendations for a page's
    semantic DOM graph.

    This is v1's stand-in for the platform's long-term AI business-intent
    classification (see pytagmanager.intent.base) -- keyword matching
    against text/class/id/aria-label instead of an LLM call, but with the
    same output shape (event, business objective, confidence, rationale)
    so a future AI classifier is a drop-in upgrade, not a rewrite.
    """
    recommendations: List[TrackingRecommendation] = []

    for node in graph.nodes:
        if node.tag in _CTA_TAGS or node.aria_role == "button":
            match = _classify(node)
            if match is None:
                continue
            keyword, objective, category, signals = match
            recommendations.append(
                TrackingRecommendation(
                    event_name=_event_name(objective),
                    trigger_type="click",
                    selector=node.stable_selector or node.css_selector,
                    selector_fallbacks=_selector_fallbacks(node),
                    event_category=category,
                    business_objective=objective,
                    confidence=_confidence(node, len(signals)),
                    rationale=f"Matched CTA keyword '{keyword}' on <{node.tag}>; signals: " + ", ".join(signals),
                    page_url=graph.url,
                )
            )

        elif node.tag == "form":
            recommendations.append(
                TrackingRecommendation(
                    event_name="form_submission",
                    trigger_type="submit",
                    selector=node.stable_selector or node.css_selector,
                    selector_fallbacks=_selector_fallbacks(node),
                    event_category="form",
                    business_objective="Lead Generation",
                    confidence=0.6 if node.stable_selector else 0.5,
                    rationale="Element is a <form>; form submissions are a default trackable business event.",
                    page_url=graph.url,
                )
            )

    return recommendations
