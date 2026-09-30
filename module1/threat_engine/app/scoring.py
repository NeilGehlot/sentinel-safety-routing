"""Weighted score. Missing signals are dropped and the remaining weights are renormalized.

1. points = scaled weight * risk for each available signal.
2. Safe-place negative contribution within the close distance.
3. isolated_night boost when its risk conditions hold.
4. distress_movement boost when movement and crowd conditions hold.
5. Clamp the sum to 0-100.

Contributor points are integers and sum to the score before clamping.
"""

from dataclasses import dataclass

from app.config import (
    INTERACTION_RULES,
    POSITIVE_WEIGHTS,
    SAFE_PLACES_CLOSE_DISTANCE_M,
    SAFE_PLACES_CLOSE_POINTS,
    SCORE_MAX,
    SCORE_MIN,
)
from app.providers.base import SignalResult
from app.schemas import Contributor


@dataclass(frozen=True)
class ScoreBreakdown:
    """Clamped score plus the integer points that produced it."""

    pre_clamp_score: int
    score: int
    contributors: tuple[Contributor, ...]


def safe_place_adjustment(distance_m: float) -> int:
    """Linear negative from the configured cap at 0 m down to 0 at the close distance."""
    if distance_m < 0 or distance_m >= SAFE_PLACES_CLOSE_DISTANCE_M:
        return 0
    if SAFE_PLACES_CLOSE_DISTANCE_M == 0:
        return 0
    fraction = 1.0 - (distance_m / SAFE_PLACES_CLOSE_DISTANCE_M)
    return round(SAFE_PLACES_CLOSE_POINTS * fraction)


def _scaled_weights(signals: list[SignalResult]) -> dict[str, float]:
    scored = {name: weight for name, weight in POSITIVE_WEIGHTS.items() if weight > 0}
    available_weight = 0
    for item in signals:
        if item.available and item.name in scored:
            available_weight += scored[item.name]
    if available_weight <= 0:
        return {}
    target = float(sum(scored.values()))
    scaled: dict[str, float] = {}
    for item in signals:
        if item.available and item.name in scored:
            scaled[item.name] = scored[item.name] / available_weight * target
    return scaled


def _risk_by_name(signals: list[SignalResult]) -> dict[str, float]:
    return {item.name: item.risk for item in signals if item.available}


def _movement_label(signals: list[SignalResult]) -> str | None:
    for item in signals:
        if item.name == "movement" and item.available:
            label = item.details.get("activity")
            if isinstance(label, str):
                return label
    return None


def _interaction_points(signals: list[SignalResult]) -> list[Contributor]:
    risks = _risk_by_name(signals)
    label = _movement_label(signals)
    contributors: list[Contributor] = []
    for rule in INTERACTION_RULES:
        if rule.movement and (label is None or label not in rule.movement):
            continue
        matched = True
        for check in rule.risk_greater_than:
            value = risks.get(check.signal)
            if value is None or value <= check.threshold:
                matched = False
                break
        if not matched:
            continue
        if rule.name == "isolated_night":
            reason = "late hour, low place density, and weak cellular signal coincide"
        else:
            reason = "movement and low place density coincide"
        contributors.append(Contributor(signal=rule.name, points=rule.points, reason=reason))
    return contributors


def score_signals(signals: list[SignalResult]) -> ScoreBreakdown:
    """Turn available signals into contributors and a clamped score."""
    scaled = _scaled_weights(signals)
    contributors: list[Contributor] = []
    for item in signals:
        weight = scaled.get(item.name)
        if weight is None or not item.available:
            continue
        points = round(weight * item.risk)
        if item.name == "safe_places":
            distance = item.details.get("distance_m")
            if isinstance(distance, (int, float)):
                points += safe_place_adjustment(float(distance))
        contributors.append(Contributor(signal=item.name, points=points, reason=item.reason))
    contributors.extend(_interaction_points(signals))
    contributors.sort(key=lambda item: item.points, reverse=True)
    pre_clamp = sum(item.points for item in contributors)
    clamped = min(SCORE_MAX, max(SCORE_MIN, pre_clamp))
    return ScoreBreakdown(
        pre_clamp_score=pre_clamp,
        score=clamped,
        contributors=tuple(contributors),
    )
