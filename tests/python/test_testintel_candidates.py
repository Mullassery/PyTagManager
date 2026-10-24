"""Tests for Phase 1.9's Test Candidate generation (docs/VISION.md §15):
grouping existing Diagnosis/consistency findings into evidence-backed
candidates, never self-certifying a "Confirmed defect"."""

from __future__ import annotations

import uuid

from pytagmanager.correlation.journey import TrackingJourney
from pytagmanager.diagnostics.models import Diagnosis
from pytagmanager.observability.events import TrackingEvent
from pytagmanager.sitewide.interaction_consistency import (
    BusinessActionConsistencyReport,
    BusinessActionImplementation,
)
from pytagmanager.testintel.candidates import (
    CATEGORY_CONSENT_BEHAVIOR,
    CATEGORY_CONSISTENCY,
    CATEGORY_EVENT_EXISTENCE,
    CATEGORY_TIMING,
    SEVERITY_CONFIRMED_DEFECT,
    SEVERITY_LEVELS,
    SEVERITY_REQUIRES_VERIFICATION,
    SEVERITY_SUSPECTED_DEFECT,
    generate_consistency_candidates,
    generate_diagnosis_candidates,
)


def _event(page_url, selector="#buy"):
    return TrackingEvent.create(
        source="browser", event_type="click", selector=selector, page_url=page_url
    )


def _journey(page_url, root_cause, confidence, business_event="add_to_cart", selector="#buy"):
    journey = TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event=business_event,
        start_time=0.0,
        end_time=1.0,
        observations=[_event(page_url, selector)],
    )
    diagnosis = Diagnosis(
        severity="critical",
        root_cause=root_cause,
        message=f"{business_event} did not fire correctly on {page_url}.",
        rule_name=root_cause,
        confidence=confidence,
    )
    return journey.with_diagnosis(diagnosis)


def _healthy_journey(page_url, business_event="add_to_cart"):
    journey = TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event=business_event,
        start_time=0.0,
        end_time=1.0,
        observations=[_event(page_url)],
    )
    return journey.with_diagnosis(Diagnosis.healthy())


# ---- generate_diagnosis_candidates ----


def test_groups_multiple_pages_with_the_same_root_cause_into_one_candidate():
    journeys = [
        _journey("https://example.com/a", "missing_datalayer_event", "Confirmed"),
        _journey("https://example.com/b", "missing_datalayer_event", "Confirmed"),
        _journey("https://example.com/c", "missing_datalayer_event", "Confirmed"),
    ]
    candidates = generate_diagnosis_candidates(journeys)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == CATEGORY_EVENT_EXISTENCE
    assert candidate.evidence_count == 3
    assert set(candidate.evidence_pages) == {
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    }


def test_healthy_journeys_produce_no_candidates():
    journeys = [_healthy_journey("https://example.com/a")]
    assert generate_diagnosis_candidates(journeys) == []


def test_journeys_without_diagnosis_produce_no_candidates():
    journey = TrackingJourney(
        journey_id=str(uuid.uuid4()),
        business_event="add_to_cart",
        start_time=0.0,
        end_time=1.0,
        observations=[],
    )
    assert generate_diagnosis_candidates([journey]) == []


def test_different_business_events_produce_separate_candidates_even_with_same_root_cause():
    journeys = [
        _journey(
            "https://example.com/a",
            "missing_datalayer_event",
            "Confirmed",
            business_event="add_to_cart",
        ),
        _journey(
            "https://example.com/b",
            "missing_datalayer_event",
            "Confirmed",
            business_event="newsletter_signup",
        ),
    ]
    candidates = generate_diagnosis_candidates(journeys)
    assert len(candidates) == 2


def test_confidence_maps_to_severity_but_never_confirmed_defect():
    journeys = [
        _journey("https://example.com/a", "missing_datalayer_event", "Confirmed"),
        _journey("https://example.com/b", "consent_blocked", "Highly likely"),
    ]
    candidates = generate_diagnosis_candidates(journeys)
    severities = {c.severity for c in candidates}
    assert SEVERITY_CONFIRMED_DEFECT not in severities
    assert SEVERITY_REQUIRES_VERIFICATION in severities  # from "Confirmed" confidence
    assert SEVERITY_SUSPECTED_DEFECT in severities  # from "Highly likely" confidence


def test_consent_blocked_maps_to_consent_behavior_category():
    journeys = [_journey("https://example.com/a", "consent_blocked", "Possible")]
    candidates = generate_diagnosis_candidates(journeys)
    assert candidates[0].category == CATEGORY_CONSENT_BEHAVIOR


def test_timing_delay_maps_to_timing_category():
    journeys = [_journey("https://example.com/a", "timing_delay", "Possible")]
    candidates = generate_diagnosis_candidates(journeys)
    assert candidates[0].category == CATEGORY_TIMING


def test_unmapped_root_cause_is_skipped_not_guessed():
    journeys = [_journey("https://example.com/a", "totally_unknown_root_cause", "Possible")]
    assert generate_diagnosis_candidates(journeys) == []


def test_suggested_verification_steps_are_populated_and_parameterized():
    journeys = [
        _journey(
            "https://example.com/a",
            "missing_datalayer_event",
            "Confirmed",
            selector="#buy-now",
        )
    ]
    candidate = generate_diagnosis_candidates(journeys)[0]
    assert candidate.suggested_verification
    assert any("#buy-now" in step for step in candidate.suggested_verification)
    assert any("add_to_cart" in step for step in candidate.suggested_verification)


# ---- generate_consistency_candidates ----


def test_inconsistent_business_action_produces_a_candidate():
    report = BusinessActionConsistencyReport(
        business_objective="Purchase Intent",
        implementations=(
            BusinessActionImplementation(
                page_url="https://example.com/product",
                selector="#buy",
                observed_event_name="add_to_cart",
                fired=True,
            ),
            BusinessActionImplementation(
                page_url="https://example.com/search",
                selector="#quick-buy",
                observed_event_name="addToCart",
                fired=True,
            ),
        ),
    )
    candidates = generate_consistency_candidates([report])
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == CATEGORY_CONSISTENCY
    assert "add_to_cart" in candidate.observed_problem
    assert "addToCart" in candidate.observed_problem
    assert set(candidate.evidence_pages) == {
        "https://example.com/product",
        "https://example.com/search",
    }


def test_consistent_business_action_produces_no_candidate():
    report = BusinessActionConsistencyReport(
        business_objective="Purchase Intent",
        implementations=(
            BusinessActionImplementation(
                page_url="https://example.com/product",
                selector="#buy",
                observed_event_name="add_to_cart",
                fired=True,
            ),
            BusinessActionImplementation(
                page_url="https://example.com/search",
                selector="#quick-buy",
                observed_event_name="add_to_cart",
                fired=True,
            ),
        ),
    )
    assert generate_consistency_candidates([report]) == []


# ---- severity scale discipline ----


def test_severity_levels_end_with_confirmed_defect_but_generators_never_emit_it():
    assert SEVERITY_LEVELS[-1] == SEVERITY_CONFIRMED_DEFECT

    journeys = [
        _journey(f"https://example.com/{i}", "missing_datalayer_event", "Confirmed")
        for i in range(3)
    ]
    report = BusinessActionConsistencyReport(
        business_objective="Purchase Intent",
        implementations=(
            BusinessActionImplementation(
                page_url="https://example.com/a",
                selector="#a",
                observed_event_name="x",
                fired=True,
            ),
            BusinessActionImplementation(
                page_url="https://example.com/b",
                selector="#b",
                observed_event_name="y",
                fired=True,
            ),
        ),
    )
    all_candidates = generate_diagnosis_candidates(journeys) + generate_consistency_candidates(
        [report]
    )
    assert all_candidates
    for candidate in all_candidates:
        assert candidate.severity != SEVERITY_CONFIRMED_DEFECT
        assert candidate.severity in SEVERITY_LEVELS
