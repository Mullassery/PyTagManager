from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pytagmanager._core import SemanticNode


@dataclass
class PageContext:
    url: str
    page_title: str = ""


@dataclass
class IntentResult:
    business_objective: str
    confidence: float
    rationale: str


@runtime_checkable
class IntentClassifier(Protocol):
    """Interface for AI-driven business intent classification (the spec's
    Phase 5). v1 ships only the deterministic rule-based classifier in
    `pytagmanager.recommend.heuristics.recommend_for_graph`; this Protocol
    is the seam a future LLM-backed implementation plugs into without
    changing callers.
    """

    def classify(self, node: SemanticNode, context: PageContext) -> IntentResult: ...


class ClaudeIntentClassifier:
    """Planned integration point: business intent classification backed by
    the Anthropic API (Claude). Not implemented in v1 -- see
    docs/ARCHITECTURE.md for the Phase 5 roadmap. Raises immediately rather
    than silently no-op'ing so callers don't mistake this for a working
    classifier.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "ClaudeIntentClassifier is a planned future feature and is not implemented yet. "
            "Use pytagmanager.recommend.heuristics.recommend_for_graph for v1's rule-based recommendations."
        )

    def classify(self, node: SemanticNode, context: PageContext) -> IntentResult:
        raise NotImplementedError
