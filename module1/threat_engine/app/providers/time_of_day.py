"""Time of day risk. Low from 07:00-19:00, peak from 00:00-04:00, linear ramps between."""

from datetime import datetime

from app.config import (
    TIME_LOW_END_HOUR,
    TIME_LOW_RISK,
    TIME_LOW_START_HOUR,
    TIME_PEAK_END_HOUR,
    TIME_PEAK_RISK,
    TIME_PEAK_START_HOUR,
)
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest


def clock_hour(moment: datetime) -> float:
    """Wall-clock hour from the timestamp, including minutes. Local fields, not UTC."""
    return moment.hour + (moment.minute / 60.0) + (moment.second / 3600.0)


def is_daytime(hour: float) -> bool:
    """True inside the low band, 07:00 inclusive through 19:00 exclusive."""
    return TIME_LOW_START_HOUR <= hour < TIME_LOW_END_HOUR


def risk_for_hour(hour: float) -> float:
    """Map a clock hour to risk using the configured bands."""
    if TIME_PEAK_START_HOUR <= hour < TIME_PEAK_END_HOUR:
        return TIME_PEAK_RISK
    if TIME_PEAK_END_HOUR <= hour < TIME_LOW_START_HOUR:
        span = TIME_LOW_START_HOUR - TIME_PEAK_END_HOUR
        fraction = (hour - TIME_PEAK_END_HOUR) / span
        return TIME_PEAK_RISK + fraction * (TIME_LOW_RISK - TIME_PEAK_RISK)
    if is_daytime(hour):
        return TIME_LOW_RISK
    span = 24.0 - TIME_LOW_END_HOUR
    fraction = (hour - TIME_LOW_END_HOUR) / span
    return TIME_LOW_RISK + fraction * (TIME_PEAK_RISK - TIME_LOW_RISK)


def _reason(hour: float) -> str:
    if TIME_PEAK_START_HOUR <= hour < TIME_PEAK_END_HOUR:
        return "it is the peak late-night hours"
    if is_daytime(hour):
        return "it is daytime"
    if hour >= TIME_LOW_END_HOUR:
        return "it is late at night"
    return "it is early morning"


def signal(request: AssessRequest) -> SignalResult:
    """Score the request timestamp. Missing timestamp is unavailable."""
    try:
        moment = request.timestamp
        if moment is None:
            return unavailable("time_of_day", "Timestamp is missing.")
        hour = clock_hour(moment)
        risk = clamp_risk(risk_for_hour(hour))
        return SignalResult(
            name="time_of_day",
            risk=risk,
            reason=_reason(hour),
            available=True,
            details={"hour": hour},
        )
    except Exception:
        return unavailable("time_of_day", "Timestamp could not be read.")
