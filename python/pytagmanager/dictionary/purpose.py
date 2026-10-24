"""Cookie/storage purpose classification (docs/VISION.md §6, Phase 1.7 item
4): classify a cookie/localStorage/sessionStorage variable's likely purpose
against a fixed taxonomy, never asserting purpose without evidence.

Mirrors `intent/ollama_classifier.py` and `sitewide/page_type.py`'s
established two-tier pattern: a deterministic classifier that collects
evidence first and is always available, plus an optional local-Ollama
classifier that re-ranks/labels *from that evidence* and falls back to the
deterministic result when Ollama isn't reachable. Every classification
carries confidence and the evidence list it's based on -- never a bare
label.

**Evidence scope, stated honestly:** what's collected here is what's
derivable from a `DictionaryVariable` alone -- the key name, how many pages
it persists across, and whether pages it was observed on carry a campaign
query parameter (available from `pages_present`, which is a tuple of full
page URLs). VISION.md §6's "consumed by an analytics request" and
"correlated with marketing scripts" evidence kinds need network-request
join data this module doesn't have access to and are not fabricated here.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import parse_qs, urlparse

from pytagmanager.dictionary.build import DictionaryVariable

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:0.5b"

PURPOSES = [
    "Identity",
    "Auth",
    "Consent",
    "Attribution",
    "Campaign",
    "Experiment",
    "Cart",
    "Preferences",
    "Session",
    "Personalization",
    "Analytics",
    "Advertising",
    "Unknown",
]

_CAMPAIGN_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "dclid",
    "ttclid",
}

# (regex matched against the lowercased key name, purpose), checked in
# order -- first match wins. Specific vendor-prefixed names (e.g. "_fbp")
# are listed before generic substrings they'd otherwise be shadowed by.
_KEY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"_fbp|_fbc|_gcl_au|doubleclick|adroll|criteo|taboola|outbrain|ad_id"),
        "Advertising",
    ),
    (re.compile(r"consent|gdpr|ccpa|onetrust|cookieyes|trustarc"), "Consent"),
    (
        re.compile(r"ab[_-]?test|experiment|variant|split[_-]?test|optimizely|vwo"),
        "Experiment",
    ),
    (re.compile(r"csrf|jwt|access[_-]?token|refresh[_-]?token|auth"), "Auth"),
    (re.compile(r"utm_|campaign|gclid|fbclid|msclkid|dclid|ttclid"), "Campaign"),
    (re.compile(r"referrer|attribution|affiliate"), "Attribution"),
    (re.compile(r"cart|basket"), "Cart"),
    (re.compile(r"lang(uage)?|locale|theme|currency|\bpref"), "Preferences"),
    (re.compile(r"personaliz|recommend|recently[_-]?viewed"), "Personalization"),
    (re.compile(r"phpsessid|jsessionid|\bsess(ion)?[_-]?id\b|^sid$"), "Session"),
    (
        re.compile(r"_ga\b|_gid|_gat|utag|analytics|amplitude|mixpanel|segment"),
        "Analytics",
    ),
    (
        re.compile(r"customer[_-]?id|user[_-]?id|\buid\b|visitor[_-]?id|client[_-]?id"),
        "Identity",
    ),
]


@dataclass(frozen=True)
class PurposeResult:
    purpose: str  # one of PURPOSES
    confidence: float
    evidence: list[str]
    rationale: str


@runtime_checkable
class PurposeClassifier(Protocol):
    def classify(self, variable: DictionaryVariable) -> PurposeResult: ...


def _campaign_url_evidence(variable: DictionaryVariable) -> bool:
    for page_url in variable.pages_present:
        query = parse_qs(urlparse(page_url).query)
        if any(param in query for param in _CAMPAIGN_QUERY_PARAMS):
            return True
    return False


def _persistence_evidence(variable: DictionaryVariable) -> str | None:
    if variable.pages_total and variable.observed_count > 1:
        ratio = variable.presence_ratio or 0.0
        return (
            f"persists across {variable.observed_count}/{variable.pages_total} pages ({ratio:.0%})"
        )
    return None


class HeuristicPurposeClassifier:
    """Deterministic fallback: key-name keyword matching plus two derived
    signals (cross-page persistence, co-occurrence with a campaign URL
    query param). Always available -- no network call, no external
    service."""

    def classify(self, variable: DictionaryVariable) -> PurposeResult:
        key = variable.path.lower()
        evidence: list[str] = []

        persistence = _persistence_evidence(variable)
        if persistence:
            evidence.append(persistence)
        if _campaign_url_evidence(variable):
            evidence.append(
                "observed on a page URL carrying a campaign query parameter (utm_*/gclid/fbclid/...)"
            )

        for pattern, purpose in _KEY_PATTERNS:
            if pattern.search(key):
                match_evidence = [
                    f"key name '{variable.path}' matches the {purpose.lower()} naming pattern"
                ] + evidence
                confidence = 0.55 + 0.1 * min(len(evidence), 3)
                return PurposeResult(
                    purpose=purpose,
                    confidence=round(min(confidence, 0.9), 2),
                    evidence=match_evidence,
                    rationale=f"Key name matched a known {purpose.lower()} naming pattern.",
                )

        if evidence:
            return PurposeResult(
                purpose="Unknown",
                confidence=0.2,
                evidence=evidence,
                rationale="No key-name pattern matched; only weak contextual evidence available.",
            )
        return PurposeResult(
            purpose="Unknown",
            confidence=0.0,
            evidence=[],
            rationale="No key-name pattern or contextual evidence matched any known purpose.",
        )


class OllamaPurposeClassifier:
    """`PurposeClassifier` backed by a local Ollama model, re-ranking from
    the same deterministic evidence `HeuristicPurposeClassifier` collects
    rather than inventing new evidence of its own. Not "Claude" -- see
    `pytagmanager.intent.ollama_classifier`'s module docstring for why that
    distinction is named explicitly rather than glossed over."""

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fallback = HeuristicPurposeClassifier()

    def is_available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def classify(self, variable: DictionaryVariable) -> PurposeResult:
        deterministic = self._fallback.classify(variable)
        if self.is_available():
            try:
                return self._classify_via_ollama(variable, deterministic)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError, KeyError):
                pass  # fall through to the deterministic result below
        return PurposeResult(
            purpose=deterministic.purpose,
            confidence=deterministic.confidence,
            evidence=deterministic.evidence,
            rationale=f"Ollama unavailable; {deterministic.rationale}",
        )

    def _build_prompt(self, variable: DictionaryVariable, deterministic: PurposeResult) -> str:
        return (
            "You are classifying the likely purpose of a website cookie/storage variable for a "
            "tagging-analytics tool. Given the variable and the deterministic evidence already "
            "collected for it, choose the single best-fitting purpose -- you may agree with the "
            "deterministic guess or override it if the evidence points elsewhere.\n\n"
            f"Source: {variable.source}\n"
            f"Key name: {variable.path}\n"
            f"Observed value types: {list(variable.value_types)}\n"
            f"Deterministic evidence collected: {deterministic.evidence or ['none']}\n"
            f"Deterministic guess: {deterministic.purpose} (confidence {deterministic.confidence})\n\n"
            f"Allowed purpose values (choose exactly one): {PURPOSES}\n\n"
            "Respond with ONLY a JSON object of the form: "
            '{"purpose": "<one of the allowed values>", '
            '"confidence": <float between 0 and 1>, '
            '"rationale": "<one short sentence>"}'
        )

    def _classify_via_ollama(
        self, variable: DictionaryVariable, deterministic: PurposeResult
    ) -> PurposeResult:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": self._build_prompt(variable, deterministic),
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
        purpose = parsed.get("purpose", "Unknown")
        if purpose not in PURPOSES:
            purpose = "Unknown"

        confidence = max(0.0, min(float(parsed.get("confidence", 0.5)), 1.0))
        rationale = str(parsed.get("rationale") or "").strip()
        rationale = (
            f"Ollama ({self.model}): {rationale}"
            if rationale
            else f"Ollama ({self.model}) classification."
        )

        return PurposeResult(
            purpose=purpose,
            confidence=confidence,
            evidence=deterministic.evidence,
            rationale=rationale,
        )
