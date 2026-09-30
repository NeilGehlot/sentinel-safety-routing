"""Nearby BLE and Wi-Fi counts.

BLE and Wi-Fi counts are a weak proxy, and a high count is not danger.
A sudden spike over the previous count for this session is only a small bump.
"""

from app.config import (
    NEARBY_CURVE,
    NEARBY_FEW_MAX_COUNT,
    NEARBY_MANY_MIN_COUNT,
    NEARBY_SPIKE_BUMP,
    NEARBY_SPIKE_MIN_INCREASE,
)
from app.providers.base import PreviousObservation, SignalResult, clamp_risk, unavailable
from app.providers.time_of_day import clock_hour, is_daytime
from app.schemas import AssessRequest


def risk_for_total(total: int) -> float:
    """Interpolate the count curve. More visible devices means lower risk."""
    knots = NEARBY_CURVE
    if not knots:
        return 0.0
    if total <= knots[0][0]:
        return clamp_risk(knots[0][1])
    if total >= knots[-1][0]:
        return clamp_risk(knots[-1][1])
    for index in range(1, len(knots)):
        right_count, right_risk = knots[index]
        if total > right_count:
            continue
        left_count, left_risk = knots[index - 1]
        span = right_count - left_count
        if span <= 0:
            return clamp_risk(right_risk)
        fraction = (total - left_count) / span
        return clamp_risk(left_risk + fraction * (right_risk - left_risk))
    return clamp_risk(knots[-1][1])


def signal(request: AssessRequest, previous: PreviousObservation | None = None) -> SignalResult:
    """Score few devices at night. A large count stays low risk."""
    try:
        nearby = request.nearby_devices
        moment = request.timestamp
        if nearby is None or moment is None:
            return unavailable("nearby_devices", "Nearby device counts are missing.")
        total = nearby.ble_count + nearby.wifi_count
        hour = clock_hour(moment)
        night = not is_daytime(hour)
        risk = risk_for_total(total)
        if total <= NEARBY_FEW_MAX_COUNT:
            reason = (
                "very few nearby devices are visible at night"
                if night
                else "few nearby devices are visible"
            )
        elif total >= NEARBY_MANY_MIN_COUNT:
            reason = "many nearby devices are visible, which is not treated as danger"
        else:
            reason = "nearby device counts look ordinary"
        spiked = False
        if previous is not None and previous.nearby_total is not None:
            increase = total - previous.nearby_total
            if increase >= NEARBY_SPIKE_MIN_INCREASE:
                risk = clamp_risk(risk + NEARBY_SPIKE_BUMP)
                spiked = True
                reason = f"{reason}, with only a small bump from a short rise in the count"
        return SignalResult(
            name="nearby_devices",
            risk=clamp_risk(risk),
            reason=reason,
            available=True,
            details={"total": float(total), "spiked": spiked},
        )
    except Exception:
        return unavailable("nearby_devices", "Nearby device counts could not be read.")
