"""LLM-backed business intent classification (docs/ARCHITECTURE.md's Phase 5
/ "AI business intent classification") implemented against a locally running
Ollama instance (https://ollama.com), not a hosted API -- this environment
has no Anthropic API credentials, so `ClaudeIntentClassifier` in
`pytagmanager.intent.base` remains the (unimplemented) seam for a real
Claude API integration later, and `OllamaIntentClassifier` here is the
actual, working `IntentClassifier` implementation: it names what's really
running rather than calling a local open-weights model "Claude".

Ollama exposes a local HTTP API (default `http://localhost:11434`); this
module talks to it with the standard library only (`urllib`), no SDK
dependency, via `/api/generate` with `format: "json"` (Ollama's structured-
output mode -- the model is constrained to emit valid JSON, which is then
parsed and validated against PyTagManager's own recommendation taxonomy).

If Ollama isn't reachable, isn't running the requested model, or returns
something that doesn't parse as a valid classification, `classify()` falls
back to the deterministic keyword-based heuristic
(`pytagmanager.recommend.heuristics.classify_node_keywords`) rather than
raising -- the same graceful-degradation shape used elsewhere in this
effort for optional local-model integrations. Every result records in its
`rationale` whether it came from the model or the fallback, so callers
(and tests) can tell which path was taken.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from pytagmanager._core import SemanticNode
from pytagmanager.intent.base import IntentResult, PageContext
from pytagmanager.recommend.heuristics import classify_node_keywords

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:0.5b"

# The fixed set of business objectives the model is asked to choose from --
# matches recommend/heuristics.py's taxonomy, plus "None" for elements with
# no discernible tracking-worthy business intent, so classifications from
# either engine (heuristic or LLM) are always comparable / interchangeable.
_TAXONOMY = [
    "Purchase Intent",
    "Trial Signup",
    "Subscription",
    "Lead Generation",
    "Authentication",
    "Content Engagement",
    "Search",
    "None",
]


class OllamaIntentClassifier:
    """`IntentClassifier` implementation backed by a local Ollama model.

    Not "Claude" -- this talks to whatever open-weights model Ollama has
    loaded locally (default `qwen2.5:0.5b`). See module docstring for why
    that distinction matters and where a real Claude API integration would
    plug in instead.
    """

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        """Best-effort liveness check against Ollama's `/api/tags` endpoint.
        Used internally by `classify()` before attempting a real call, and
        exposed publicly so tests/callers can skip/branch without paying
        for a full generate call."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def classify(self, node: SemanticNode, context: PageContext) -> IntentResult:
        if self.is_available():
            try:
                return self._classify_via_ollama(node, context)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError, KeyError):
                pass  # fall through to the deterministic fallback below
        return self._fallback(node)

    # -- Ollama call ---------------------------------------------------

    def _build_prompt(self, node: SemanticNode, context: PageContext) -> str:
        return (
            "You are classifying a single HTML element's business intent for a "
            "website analytics tool. Given the element below, choose the single "
            "best-fitting business objective.\n\n"
            f"Page URL: {context.url}\n"
            f"Page title: {context.page_title}\n"
            f"Element tag: <{node.tag}>\n"
            f"Visible text: {node.text!r}\n"
            f"CSS classes: {list(node.classes)}\n"
            f"ARIA label: {node.aria_label!r}\n"
            f"ARIA role: {node.aria_role!r}\n\n"
            f"Allowed business_objective values (choose exactly one): {_TAXONOMY}\n\n"
            "Respond with ONLY a JSON object of the form: "
            '{"business_objective": "<one of the allowed values>", '
            '"confidence": <float between 0 and 1>, '
            '"rationale": "<one short sentence>"}'
        )

    def _classify_via_ollama(self, node: SemanticNode, context: PageContext) -> IntentResult:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": self._build_prompt(node, context),
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

        raw_response = body.get("response", "")
        parsed = json.loads(raw_response)

        objective = parsed.get("business_objective", "None")
        if objective not in _TAXONOMY:
            objective = "None"

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(confidence, 1.0))

        rationale = str(parsed.get("rationale") or "").strip()
        if not rationale:
            rationale = f"Ollama ({self.model}) classification."
        else:
            rationale = f"Ollama ({self.model}): {rationale}"

        return IntentResult(business_objective=objective, confidence=confidence, rationale=rationale)

    # -- fallback --------------------------------------------------------

    def _fallback(self, node: SemanticNode) -> IntentResult:
        """Deterministic keyword-based classification, used when Ollama is
        unreachable/unusable. Same taxonomy, same output shape -- callers
        never see a different `IntentResult` structure depending on which
        path was taken, only a rationale explaining which one was."""
        match: Optional[tuple] = classify_node_keywords(node)
        if match is None:
            return IntentResult(
                business_objective="None",
                confidence=0.0,
                rationale="Ollama unavailable; deterministic keyword fallback found no matching signal.",
            )
        keyword, objective, _category, signals = match
        return IntentResult(
            business_objective=objective,
            confidence=0.5,
            rationale=(
                f"Ollama unavailable; deterministic keyword fallback matched '{keyword}': " + ", ".join(signals)
            ),
        )
