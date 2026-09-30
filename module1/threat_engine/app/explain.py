"""Summary and recommendations. The rule strings are the fallback.

A configured LLM may phrase the summary from the supplied contributors,
predicted scores, and live context. It does not receive permission to change
the score or the contributor points. A missing key, timeout, or bad JSON
keeps the rule-based strings. Copy stays calm. It does not invent places or
incidents, and it never says the user is being followed or attacked.
"""

from dataclasses import dataclass
from typing import Any

from app.config import (
    BATTERY_LOW_PCT,
    CELLULAR_ADVISORY_DBM,
    MAX_RECOMMENDATIONS,
    MOCK_SAFE_PLACE_LABEL,
    SUMMARY_ELEVATED_AT,
    SUMMARY_HIGH_AT,
)
from app.llm import may_phrase, phrase_explanation
from app.schemas import Contributor, Explanation, PredictedScore


@dataclass(frozen=True)
class ExplainContext:
    """Facts already measured on this request. Missing facts stay None."""

    battery_pct: float | None = None
    internet_available: bool | None = None
    cellular_dbm: float | None = None
    safe_distance_m: float | None = None
    safe_place_name: str | None = None
    safe_place_direction: str | None = None
    movement_label: str | None = None


def _summary(score: int, contributors: tuple[Contributor, ...] | list[Contributor]) -> str:
    drivers = [item for item in contributors if item.points > 0][:3]
    if not drivers:
        return "Your score has no strong raising factors in the current signals."
    reasons = "; ".join(item.reason.rstrip(".") for item in drivers)
    if score >= SUMMARY_HIGH_AT:
        lead = "Your score is high mainly because"
    elif score >= SUMMARY_ELEVATED_AT:
        lead = "Your score is elevated mainly because"
    else:
        lead = "Your score is low. The largest factors are"
    return f"{lead} {reasons}."


def _recommendations(context: ExplainContext) -> list[str]:
    items: list[str] = []
    label = context.movement_label
    if label == "fall":
        items.append(
            "Movement looks like a fall. If you can, move toward the nearest safe place."
        )
    elif label == "sudden_stop":
        items.append(
            "Speed dropped suddenly. If you can, continue toward the nearest safe place."
        )
    elif label == "running":
        items.append(
            "Movement looks like running. If you can, slow to a walk and head toward the nearest safe place."
        )
    if context.safe_distance_m is not None:
        distance = round(context.safe_distance_m)
        name = context.safe_place_name
        direction = context.safe_place_direction
        generic = name is None or name == MOCK_SAFE_PLACE_LABEL
        if not generic and direction:
            items.append(f"{name} is about {distance} m {direction}.")
        elif not generic and name is not None:
            items.append(f"{name} is about {distance} m away.")
        else:
            items.append(f"The nearest safe place is about {distance} m away.")
    if context.battery_pct is not None and context.battery_pct < BATTERY_LOW_PCT:
        items.append(
            f"Your battery is at {context.battery_pct:g}%. Consider enabling battery saver."
        )
    if context.internet_available is False:
        items.append("Internet is unavailable, so this result used the on-device rules.")
    if context.cellular_dbm is not None and context.cellular_dbm <= CELLULAR_ADVISORY_DBM:
        items.append("Cellular signal is very weak.")
    return items[:MAX_RECOMMENDATIONS]


def _payload(
    score: int,
    contributors: tuple[Contributor, ...] | list[Contributor],
    context: ExplainContext,
    predicted: list[PredictedScore] | None,
) -> dict[str, Any]:
    """Facts the phrasing step is allowed to use. Numbers stay as already scored."""
    horizons = []
    for item in predicted or []:
        horizons.append({"horizon_min": item.horizon_min, "score": item.score})
    return {
        "current_score": score,
        "contributors": [
            {"signal": item.signal, "points": item.points, "reason": item.reason}
            for item in contributors
        ],
        "predicted": horizons,
        "context": {
            "battery_pct": context.battery_pct,
            "internet_available": context.internet_available,
            "cellular_dbm": context.cellular_dbm,
            "safe_distance_m": context.safe_distance_m,
            "safe_place_name": context.safe_place_name,
            "safe_place_direction": context.safe_place_direction,
            "movement_label": context.movement_label,
        },
    }


def explain(
    score: int,
    contributors: tuple[Contributor, ...] | list[Contributor],
    context: ExplainContext,
    predicted: list[PredictedScore] | None = None,
) -> tuple[Explanation, list[str]]:
    """Build the section 5 explanation. Contributor points are passed through."""
    summary = _summary(score, contributors)
    recommendations = _recommendations(context)
    phrased = None
    if may_phrase():
        try:
            phrased = phrase_explanation(_payload(score, contributors, context, predicted))
        except Exception:
            phrased = None
    if phrased is not None:
        summary = str(phrased["summary"])
        recommendations = [str(item) for item in phrased["recommendations"]][:MAX_RECOMMENDATIONS]
    return (
        Explanation(summary=summary, contributors=list(contributors)),
        recommendations,
    )
