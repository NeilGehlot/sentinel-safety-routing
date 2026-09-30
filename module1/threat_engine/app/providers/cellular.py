"""Cellular risk. Weaker dBm raises risk. One reading, no history."""

from app.config import CELLULAR_ADVISORY_DBM
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest


def risk_for_dbm(dbm: float) -> float:
    """Stateless risk. -70 dBm is 0 and 55 dBm weaker is 1."""
    return clamp_risk((-70.0 - dbm) / 55.0)


def signal(request: AssessRequest) -> SignalResult:
    """Score cellular_dbm. A missing device block is unavailable."""
    try:
        device = request.device
        if device is None:
            return unavailable("cellular", "Cellular signal is missing.")
        dbm = device.cellular_dbm
        risk = risk_for_dbm(dbm)
        if dbm <= CELLULAR_ADVISORY_DBM:
            reason = "cellular signal is very weak"
        else:
            reason = "cellular signal is usable"
        return SignalResult(
            name="cellular",
            risk=risk,
            reason=reason,
            available=True,
            details={"cellular_dbm": dbm},
        )
    except Exception:
        return unavailable("cellular", "Cellular signal could not be read.")
