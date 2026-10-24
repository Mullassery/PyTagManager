"""Duplicate/conflicting implementation detection (docs/VISION.md §17,
Phase 1.85 item 2): flags static candidates for duplicate instrumentation
(two GTM containers, GTM alongside a hard-coded vendor equivalent, the
same vendor wired in twice with different IDs) but -- deliberately --
never reports a static candidate alone as a finding. A site can run two
GTM containers for two unrelated business units without ever double-firing
the same event; the static shape alone is not evidence of a real problem.

A candidate only escalates to a `DuplicateFinding` once *runtime* evidence
corroborates it: the same business interaction (Phase 1.8's
`InteractionTrace`, not raw `TrackingJourney`s, per the roadmap) produced
more than one analytics network request. Even then, this module cannot
attribute a specific network request to a specific static implementation
(GTM's own network traffic and a hard-coded gtag() call can both land on
the exact same GA4 collect endpoint, indistinguishable from the outside) --
the finding names what's *consistent* with the static candidates, hedged
accordingly, not a per-request attribution that isn't actually observable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pytagmanager.diagnostics.trace import InteractionTrace, InteractionTraceStep
from pytagmanager.tagexec.static_scan import StaticScanResult

CANDIDATE_MULTIPLE_GTM_CONTAINERS = "multiple_gtm_containers"
CANDIDATE_GTM_PLUS_HARDCODED_VENDOR = "gtm_plus_hardcoded_vendor"
CANDIDATE_DUPLICATE_VENDOR_IMPLEMENTATION = "duplicate_vendor_implementation"

# Vendors whose category is "analytics" and whose events GTM containers
# commonly *also* send (via a GA4/Adobe tag configured inside the
# container) -- so a hard-coded implementation of one of these alongside
# a GTM container is a real double-tracking candidate, unlike e.g. a
# hard-coded chat widget alongside GTM, which has no overlap to duplicate.
_GTM_OVERLAPPING_VENDOR_CATEGORIES = frozenset({"analytics"})


@dataclass(frozen=True)
class DuplicateCandidate:
    kind: str
    description: str
    involved: tuple[str, ...]  # GTM container IDs and/or vendor names, human-readable


@dataclass(frozen=True)
class RuntimeDuplicateEvidence:
    journey_id: str
    business_event: str
    request_count: int
    request_urls: tuple[str, ...]
    payload_similarity: float  # 0.0-1.0, Jaccard similarity of request query params


@dataclass(frozen=True)
class DuplicateFinding:
    candidate: DuplicateCandidate
    runtime_evidence: tuple[RuntimeDuplicateEvidence, ...]
    confidence: str = "Highly likely"

    @property
    def message(self) -> str:
        evidence = self.runtime_evidence[0]
        detail = (
            f"'{evidence.business_event}' produced {evidence.request_count} analytics network "
            f"requests ({evidence.payload_similarity:.0%} payload-parameter overlap)"
        )
        if len(self.runtime_evidence) > 1:
            detail += f", and {len(self.runtime_evidence) - 1} more interaction(s) showed the same pattern"
        return (
            f"{self.candidate.description} ({', '.join(self.candidate.involved)}); {detail} -- consistent "
            "with duplicate instrumentation, though attributing a specific request to a specific "
            "implementation isn't directly observable from network traffic alone."
        )


def find_duplicate_candidates(scan: StaticScanResult) -> list[DuplicateCandidate]:
    candidates: list[DuplicateCandidate] = []

    if scan.has_multiple_gtm_containers:
        candidates.append(
            DuplicateCandidate(
                kind=CANDIDATE_MULTIPLE_GTM_CONTAINERS,
                description="Multiple GTM containers detected on the same page",
                involved=scan.gtm_container_ids,
            )
        )

    if scan.gtm_containers:
        for vendor in scan.vendors:
            if vendor.category in _GTM_OVERLAPPING_VENDOR_CATEGORIES:
                candidates.append(
                    DuplicateCandidate(
                        kind=CANDIDATE_GTM_PLUS_HARDCODED_VENDOR,
                        description=(
                            f"GTM container present alongside a hard-coded {vendor.vendor} implementation "
                            "-- GTM containers commonly also fire this vendor's tag"
                        ),
                        involved=scan.gtm_container_ids + (vendor.vendor,),
                    )
                )

    by_vendor: dict = {}
    for vendor in scan.vendors:
        by_vendor.setdefault(vendor.vendor, []).append(vendor)
    for vendor_name, detections in by_vendor.items():
        distinct_evidence = {d.evidence for d in detections}
        if len(distinct_evidence) > 1:
            candidates.append(
                DuplicateCandidate(
                    kind=CANDIDATE_DUPLICATE_VENDOR_IMPLEMENTATION,
                    description=f"{vendor_name} wired in more than once with distinct IDs/snippets",
                    involved=tuple(sorted(distinct_evidence)),
                )
            )

    return candidates


def _query_params(step: InteractionTraceStep) -> dict:
    return step.payload.get("params", {}) if isinstance(step.payload, dict) else {}


def _payload_similarity(a: dict, b: dict) -> float:
    """Jaccard similarity over (key, value) pairs -- 1.0 means identical
    parameter sets, 0.0 means no overlap. Symmetric, order-independent."""
    pairs_a = set(a.items())
    pairs_b = set(b.items())
    union = pairs_a | pairs_b
    if not union:
        return 0.0
    return len(pairs_a & pairs_b) / len(union)


def find_runtime_duplicate_evidence(
    trace: InteractionTrace,
) -> RuntimeDuplicateEvidence | None:
    """Evidence of duplicate analytics traffic for one interaction: more
    than one network_request step in its trace. `payload_similarity`
    compares the first two such requests' query parameters -- a proxy for
    "these two requests carry the same business data," not proof the
    requests are byte-identical."""
    network_steps = [s for s in trace.steps if s.event_type == "network_request"]
    if len(network_steps) < 2:
        return None
    similarity = _payload_similarity(
        _query_params(network_steps[0]), _query_params(network_steps[1])
    )
    return RuntimeDuplicateEvidence(
        journey_id=trace.journey_id,
        business_event=trace.business_event,
        request_count=len(network_steps),
        request_urls=tuple(
            s.payload.get("url", "") for s in network_steps if isinstance(s.payload, dict)
        ),
        payload_similarity=similarity,
    )


def analyze_duplicates(
    scan: StaticScanResult, traces: Sequence[InteractionTrace]
) -> list[DuplicateFinding]:
    """The only public entry point that produces `DuplicateFinding`s --
    static candidates with no corroborating runtime evidence are silently
    dropped, per this module's docstring. Call `find_duplicate_candidates()`
    directly if a lower-confidence "candidate, unconfirmed" view is ever
    needed instead."""
    candidates = find_duplicate_candidates(scan)
    if not candidates:
        return []

    runtime_evidence = tuple(
        e for e in (find_runtime_duplicate_evidence(t) for t in traces) if e is not None
    )
    if not runtime_evidence:
        return []

    return [
        DuplicateFinding(candidate=candidate, runtime_evidence=runtime_evidence)
        for candidate in candidates
    ]
