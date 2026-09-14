"""Presence-vs-availability labeling (docs/VISION.md §4, Phase 1.7 item 2):
a variable existing somewhere in the app is not the same as GTM being able
to use it. This module ships the page-load-signal subset of the five-level
scale -- Exists / Exposed / Accessible -- that's derivable from a
`DictionaryVariable`'s `source` alone. "Available at trigger time" and
"Consistently populated" need Phase 1.8's interaction-timing data and are
deliberately not attempted here (see docs/ROADMAP.md Phase 1.7).

The Accessible label is a claim about which built-in GTM variable type
*could* read the value, not proof a container actually does -- it is
evidence-based (the mechanism exists) rather than confirmation (a real
container was checked), and is worded accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass

from pytagmanager.dictionary.build import DictionaryVariable

EXISTS = "Exists"
EXPOSED = "Exposed"
ACCESSIBLE = "Accessible"
POSSIBLY_ACCESSIBLE = "Possibly accessible"
NOT_ACCESSIBLE = "Not accessible"


@dataclass(frozen=True)
class PresenceLabel:
    exists: bool
    exposed: bool
    accessibility: str  # one of ACCESSIBLE / POSSIBLY_ACCESSIBLE / NOT_ACCESSIBLE
    rationale: str


def label_presence(variable: DictionaryVariable) -> PresenceLabel:
    """Every observed variable by definition Exists (it was captured), so
    the real signal here is `exposed` (is it in a GTM-readable surface at
    all) and `accessibility` (which built-in GTM variable mechanism, if
    any, could read it)."""
    if variable.source in ("datalayer_event", "datalayer_field"):
        return PresenceLabel(
            exists=True,
            exposed=True,
            accessibility=ACCESSIBLE,
            rationale="Observed in window.dataLayer; GTM's built-in Data Layer Variable type reads this directly.",
        )
    if variable.source == "cookie":
        return PresenceLabel(
            exists=True,
            exposed=False,
            accessibility=ACCESSIBLE,
            rationale=(
                "Observed as a cookie, not in dataLayer; GTM's built-in 1st Party Cookie variable "
                "type can read any cookie by name, so this is accessible without custom code."
            ),
        )
    # local_storage / session_storage
    return PresenceLabel(
        exists=True,
        exposed=False,
        accessibility=POSSIBLY_ACCESSIBLE,
        rationale=(
            f"Observed in {variable.source.replace('_', ' ')}, not in dataLayer. GTM has no built-in "
            "variable type for localStorage/sessionStorage -- reading it requires a hand-written Custom "
            "JavaScript variable, whose existence in any given container can't be confirmed from "
            "runtime observation alone."
        ),
    )
