"""GPS context. This signal is not scored. It only carries lat, lon, speed, and heading."""

from app.providers.base import SignalResult, unavailable
from app.schemas import AssessRequest


def signal(request: AssessRequest) -> SignalResult:
    """Return the location fields. Weight stays 0 in config, so scoring skips it."""
    try:
        location = request.location
        if location is None:
            return unavailable("gps", "Location is missing.")
        return SignalResult(
            name="gps",
            risk=0.0,
            reason="Location, speed, and heading are available.",
            available=True,
            details={
                "lat": location.lat,
                "lon": location.lon,
                "speed_mps": location.speed_mps,
                "heading_deg": location.heading_deg,
            },
        )
    except Exception:
        return unavailable("gps", "Location could not be read.")
