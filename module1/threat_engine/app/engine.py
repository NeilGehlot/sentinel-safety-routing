"""Run the rule-based providers, score them, and explain the result.

Session memory for sudden stops and nearby-device spikes lives here.
Predicted scores project the current speed and heading. They are not a forecast.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.explain import ExplainContext, explain
from app.providers import cellular, connectivity, crime_risk, crowd_density, gps_context
from app.providers import movement, nearby_devices, news_risk, safe_places, time_of_day, weather
from app.providers.base import PreviousObservation, SignalResult, unavailable
from app.prediction import predict_scores
from app.schemas import AssessRequest, AssessResponse
from app.scoring import score_signals


@dataclass
class _Memory:
    speed_mps: float | None
    observed_at: datetime
    nearby_total: int | None


_SESSIONS: dict[str, _Memory] = {}


def reset_session_memory() -> None:
    """Drop in-engine session memory. Tests call this between cases."""
    _SESSIONS.clear()


def _previous(session_id: str | None) -> PreviousObservation | None:
    if not session_id:
        return None
    stored = _SESSIONS.get(session_id)
    if stored is None:
        return None
    return PreviousObservation(
        speed_mps=stored.speed_mps,
        observed_at=stored.observed_at,
        nearby_total=stored.nearby_total,
    )


def _remember(request: AssessRequest) -> None:
    session_id = request.session_id
    if not session_id:
        return
    nearby_total: int | None = None
    if request.nearby_devices is not None:
        nearby_total = request.nearby_devices.ble_count + request.nearby_devices.wifi_count
    speed = request.location.speed_mps if request.location is not None else None
    _SESSIONS[session_id] = _Memory(
        speed_mps=speed,
        observed_at=request.timestamp,
        nearby_total=nearby_total,
    )


def _guard(name: str, fn: Callable[[], SignalResult]) -> SignalResult:
    try:
        return fn()
    except Exception:
        return unavailable(name, "Signal could not be read.")


def collect_signals(request: AssessRequest, previous: PreviousObservation | None) -> list[SignalResult]:
    """Call every provider. A failure becomes available=False and does not raise."""
    previous_speed = previous.speed_mps if previous is not None else None
    previous_at = previous.observed_at if previous is not None else None
    signals = [
        _guard("gps", lambda: gps_context.signal(request)),
        _guard("time_of_day", lambda: time_of_day.signal(request)),
        _guard("weather", lambda: weather.signal(request)),
        _guard("crime_risk", lambda: crime_risk.signal(request)),
        _guard("news_risk", lambda: news_risk.signal(request)),
        _guard("crowd_density", lambda: crowd_density.signal(request)),
        _guard("cellular", lambda: cellular.signal(request)),
        _guard("safe_places", lambda: safe_places.signal(request)),
        _guard("nearby_devices", lambda: nearby_devices.signal(request, previous)),
        _guard(
            "movement",
            lambda: movement.signal(request, previous_speed, previous_at),
        ),
    ]
    try:
        signals.extend(connectivity.signals(request))
    except Exception:
        signals.append(unavailable("connectivity_battery", "Battery level could not be read."))
        signals.append(unavailable("connectivity_internet", "Internet status could not be read."))
    return signals


def _context(request: AssessRequest, signals: list[SignalResult]) -> ExplainContext:
    battery_pct = request.device.battery_pct if request.device is not None else None
    internet = request.device.internet_available if request.device is not None else None
    cellular_dbm = request.device.cellular_dbm if request.device is not None else None
    safe_distance: float | None = None
    safe_name: str | None = None
    safe_direction: str | None = None
    movement_label: str | None = None
    for item in signals:
        if item.name == "safe_places" and item.available:
            distance = item.details.get("distance_m")
            if isinstance(distance, (int, float)):
                safe_distance = float(distance)
            label = item.details.get("label")
            if isinstance(label, str):
                safe_name = label
            direction = item.details.get("direction")
            if isinstance(direction, str):
                safe_direction = direction
        if item.name == "movement" and item.available:
            label = item.details.get("activity")
            if isinstance(label, str):
                movement_label = label
    return ExplainContext(
        battery_pct=battery_pct,
        internet_available=internet,
        cellular_dbm=cellular_dbm,
        safe_distance_m=safe_distance,
        safe_place_name=safe_name,
        safe_place_direction=safe_direction,
        movement_label=movement_label,
    )


async def assess(request: AssessRequest) -> AssessResponse:
    """Score one snapshot and project that score 5 and 10 minutes ahead."""
    previous = _previous(request.session_id)
    signals = collect_signals(request, previous)
    breakdown = score_signals(signals)
    predicted = predict_scores(request, signals)
    explanation, recommendations = explain(
        breakdown.score,
        breakdown.contributors,
        _context(request, signals),
        predicted,
    )
    _remember(request)
    session_id = request.session_id if request.session_id else ""
    return AssessResponse(
        session_id=session_id,
        current_score=breakdown.score,
        predicted=predicted,
        explanation=explanation,
        recommendations=recommendations,
    )
