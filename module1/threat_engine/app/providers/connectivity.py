"""Battery and internet. Two separate signals, not one combined result."""

from app.config import INTERNET_AVAILABLE_RISK, INTERNET_UNAVAILABLE_RISK
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest


def _battery(pct: float) -> SignalResult:
    """Linear and stateless. A full battery is 0 and an empty battery is 1."""
    risk = clamp_risk((100.0 - pct) / 100.0)
    if risk > 0.5:
        reason = f"Battery at {pct:g}%"
    else:
        reason = "Battery is fine"
    return SignalResult(
        name="battery",
        risk=risk,
        reason=reason,
        available=True,
        details={"battery_pct": pct},
    )


def _internet(available: bool) -> SignalResult:
    if available:
        return SignalResult(
            name="internet",
            risk=clamp_risk(INTERNET_AVAILABLE_RISK),
            reason="internet is available",
            available=True,
            details={"internet_available": True},
        )
    return SignalResult(
        name="internet",
        risk=clamp_risk(INTERNET_UNAVAILABLE_RISK),
        reason="internet is unavailable",
        available=True,
        details={"internet_available": False},
    )


def signals(request: AssessRequest) -> list[SignalResult]:
    """Return battery and internet. Both are unavailable when the device block is missing."""
    try:
        device = request.device
        if device is None:
            return [
                unavailable("battery", "Battery level is missing."),
                unavailable("internet", "Internet status is missing."),
            ]
        return [_battery(device.battery_pct), _internet(device.internet_available)]
    except Exception:
        return [
            unavailable("battery", "Battery level could not be read."),
            unavailable("internet", "Internet status could not be read."),
        ]
