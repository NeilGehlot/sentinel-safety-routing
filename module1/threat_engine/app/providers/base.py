"""Shared signal result. Providers return this and do not raise on missing data."""

from dataclasses import dataclass, field
from datetime import datetime

from app.config import SIGNAL_RISK_MAX, SIGNAL_RISK_MIN


@dataclass(frozen=True)
class PreviousObservation:
    """Last speed and device count for one session. The engine owns the store."""

    speed_mps: float | None = None
    observed_at: datetime | None = None
    nearby_total: int | None = None


@dataclass(frozen=True)
class SignalResult:
    """One signal. risk is on 0..1. available is False when the input is missing."""

    name: str
    risk: float
    reason: str
    available: bool
    details: dict[str, float | str | bool | None] = field(default_factory=dict)


def clamp_risk(value: float) -> float:
    """Keep a risk inside the configured 0..1 scale."""
    if value < SIGNAL_RISK_MIN:
        return SIGNAL_RISK_MIN
    if value > SIGNAL_RISK_MAX:
        return SIGNAL_RISK_MAX
    return value


def unavailable(name: str, reason: str) -> SignalResult:
    """A missing signal. Scoring drops it instead of treating it as zero risk."""
    return SignalResult(name=name, risk=SIGNAL_RISK_MIN, reason=reason, available=False)
