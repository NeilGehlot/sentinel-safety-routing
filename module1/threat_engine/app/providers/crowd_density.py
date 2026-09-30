"""Crowd risk from a place-density proxy, adjusted by time of day.

This is a stand-in for a later OSM place-density query. It is not a phone sensor
and it does not call Overpass.
"""

from app.config import (
    CROWD_DAY_MULTIPLIER,
    CROWD_NIGHT_MULTIPLIER,
    MOCK_PLACE_DENSITY,
)
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.providers.time_of_day import clock_hour, is_daytime
from app.schemas import AssessRequest


def place_density(lat: float, lon: float) -> float:
    """Deterministic mock density in 0..1. The coordinates are accepted for the later OSM call."""
    _ = (lat, lon)
    return MOCK_PLACE_DENSITY


def signal(request: AssessRequest) -> SignalResult:
    """Low place density raises isolation risk, more so outside the daytime band."""
    try:
        location = request.location
        moment = request.timestamp
        if location is None or moment is None:
            return unavailable("crowd_density", "Location or timestamp is missing.")
        density = clamp_risk(place_density(location.lat, location.lon))
        isolation = 1.0 - density
        hour = clock_hour(moment)
        multiplier = CROWD_DAY_MULTIPLIER if is_daytime(hour) else CROWD_NIGHT_MULTIPLIER
        risk = clamp_risk(isolation * multiplier)
        if is_daytime(hour):
            reason = f"the place density proxy is {density:.2f} during daytime"
        else:
            reason = f"the place density proxy is {density:.2f} at this hour"
        return SignalResult(
            name="crowd_density",
            risk=risk,
            reason=reason,
            available=True,
            details={"place_density": density, "hour": hour},
        )
    except Exception:
        return unavailable("crowd_density", "Place density could not be read.")
