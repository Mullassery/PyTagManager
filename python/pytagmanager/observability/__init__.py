from pytagmanager.observability.events import TrackingEvent

__all__ = [
    "ObservationSession",
    "Scenario",
    "TrackingEvent",
    "auto_scenario_from_recommendations",
]


def __getattr__(name: str):
    if name in {"Scenario", "auto_scenario_from_recommendations"}:
        from pytagmanager.observability.scenario import (
            Scenario,
            auto_scenario_from_recommendations,
        )

        globals()["Scenario"] = Scenario
        globals()["auto_scenario_from_recommendations"] = auto_scenario_from_recommendations
        return globals()[name]
    if name == "ObservationSession":
        from pytagmanager.observability.session import ObservationSession

        globals()["ObservationSession"] = ObservationSession
        return ObservationSession
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
