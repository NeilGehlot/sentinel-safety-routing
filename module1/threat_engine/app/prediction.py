"""Project the current snapshot 5 and 10 minutes ahead.

This is projection along the current heading and speed, not a forecast.
It does not use randomness. A speed under the stationary threshold keeps
the same position.
"""

import math
from collections.abc import Callable
from datetime import timedelta

from app import config
from app.providers import connectivity, crime_risk, crowd_density, news_risk, safe_places, time_of_day, weather
from app.providers.base import SignalResult, unavailable
from app.schemas import AssessRequest, DeviceState, PredictedScore
from app.scoring import score_signals

LocationScorer = Callable[[AssessRequest], SignalResult]

# Re-scored at the projected point and time. Device signals are carried forward.
_LOCATION_SCORERS: tuple[tuple[str, LocationScorer], ...] = (
    ("time_of_day", time_of_day.signal),
    ("weather", weather.signal),
    ("crime_risk", crime_risk.signal),
    ("news_risk", news_risk.signal),
    ("crowd_density", crowd_density.signal),
    ("safe_places", safe_places.signal),
)


def project_position(
    lat: float,
    lon: float,
    speed_mps: float | None,
    heading_deg: float | None,
    horizon_min: int,
) -> tuple[float, float]:
    """Hold the point when heading is missing or speed is under 0.3 m/s.

    The caller still moves the timestamp forward. Only a known heading and
    speed at or above the stationary threshold change the coordinates.
    """
    if speed_mps is None or heading_deg is None or speed_mps < config.STATIONARY_SPEED_MPS:
        return lat, lon
    seconds = timedelta(minutes=horizon_min).total_seconds()
    distance_m = speed_mps * seconds
    if distance_m <= 0 or config.EARTH_RADIUS_M <= 0:
        return lat, lon
    angular = distance_m / config.EARTH_RADIUS_M
    bearing = math.radians(heading_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def decay_battery(battery_pct: float, horizon_min: int) -> float:
    """Drop the configured percent for each decay interval. Never below zero."""
    steps = horizon_min / config.BATTERY_DECAY_INTERVAL_MIN
    decayed = battery_pct - (config.BATTERY_DECAY_PERCENT_PER_5_MIN * steps)
    if decayed < 0:
        return 0.0
    return decayed


def _guard(name: str, fn: Callable[[], SignalResult]) -> SignalResult:
    try:
        return fn()
    except Exception:
        return unavailable(name, "Signal could not be read.")


def _carried(current: dict[str, SignalResult], name: str, reason: str) -> SignalResult:
    found = current.get(name)
    if found is not None:
        return found
    return unavailable(name, reason)


def _battery_signal(future: AssessRequest, current: dict[str, SignalResult]) -> SignalResult:
    if future.device is None:
        return _carried(current, "connectivity_battery", "Battery level is missing.")
    try:
        for item in connectivity.signals(future):
            if item.name == "connectivity_battery":
                return item
    except Exception:
        return unavailable("connectivity_battery", "Battery level could not be read.")
    return unavailable("connectivity_battery", "Battery level could not be read.")


def _future_request(
    request: AssessRequest,
    lat: float,
    lon: float,
    horizon_min: int,
) -> AssessRequest:
    device: DeviceState | None = None
    if request.device is not None:
        device = request.device.model_copy(
            update={"battery_pct": decay_battery(request.device.battery_pct, horizon_min)}
        )
    location = request.location.model_copy(update={"lat": lat, "lon": lon})
    return request.model_copy(
        update={
            "timestamp": request.timestamp + timedelta(minutes=horizon_min),
            "location": location,
            "device": device,
        }
    )


def score_horizon(
    request: AssessRequest,
    current_signals: list[SignalResult],
    horizon_min: int,
) -> int:
    """Re-score location signals at the projected point and carry the device signals."""
    lat, lon = project_position(
        request.location.lat,
        request.location.lon,
        request.location.speed_mps,
        request.location.heading_deg,
        horizon_min,
    )
    future = _future_request(request, lat, lon, horizon_min)
    carried = {item.name: item for item in current_signals}
    signals: list[SignalResult] = []
    for name, scorer in _LOCATION_SCORERS:
        signals.append(_guard(name, lambda scorer=scorer: scorer(future)))
    signals.append(_carried(carried, "cellular", "Cellular signal is missing."))
    signals.append(_battery_signal(future, carried))
    signals.append(_carried(carried, "connectivity_internet", "Internet status is missing."))
    signals.append(_carried(carried, "nearby_devices", "Nearby device counts are missing."))
    signals.append(_carried(carried, "movement", "Movement is missing."))
    return score_signals(signals).score


def predict_scores(request: AssessRequest, current_signals: list[SignalResult]) -> list[PredictedScore]:
    """Return section 5 horizon scores. Each item is only horizon_min and score."""
    predicted: list[PredictedScore] = []
    for horizon in config.PREDICTION_HORIZONS_MIN:
        predicted.append(
            PredictedScore(
                horizon_min=horizon,
                score=score_horizon(request, current_signals, horizon),
            )
        )
    return predicted
