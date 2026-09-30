"""
Centralised, env-driven configuration.

All Sentinel routing/safety thresholds and API configuration
are loaded from the project's root .env file.
"""

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


# ============================================================
# PROJECT ROOT
# ============================================================
#
# Current file:
# sentinel/
#   module2/
#     app/
#       config.py  <-- this file
#
# parents[0] = app/
# parents[1] = module2/
# parents[2] = sentinel/
#
# Therefore parents[2] is the project root.
#

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Root .env file:
# sentinel/.env
ENV_FILE = PROJECT_ROOT / ".env"

# Load environment variables from the root .env
load_dotenv(ENV_FILE)


# ============================================================
# HELPER
# ============================================================

def _float(key: str, default: float) -> float:
    """Read a float from the environment."""
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _int(key: str, default: int) -> int:
    """Read an integer from the environment."""
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


# ============================================================
# SETTINGS
# ============================================================

@dataclass(frozen=True)
class Settings:

    # --------------------------------------------------------
    # OpenRouteService
    # --------------------------------------------------------

    ors_api_key: str = os.getenv("ORS_API_KEY", "").strip()

    # --------------------------------------------------------
    # Incident / route scoring
    # --------------------------------------------------------

    radius: float = _float(
        "INCIDENT_ROUTE_RADIUS_METERS",
        500
    )

    critical: float = _float(
        "CRITICAL_SAFETY_THRESHOLD",
        60
    )

    min_improve: float = _float(
        "MIN_SAFETY_IMPROVEMENT",
        15
    )

    max_extra: float = _float(
        "MAX_EXTRA_TRAVEL_MINUTES",
        10
    )

    # --------------------------------------------------------
    # Demo mode
    # --------------------------------------------------------

    demo_mode: bool = (
        os.getenv("DEMO_MODE", "true").lower() == "true"
    )

    # --------------------------------------------------------
    # Polling
    # --------------------------------------------------------

    poll: int = _int(
        "POLLING_INTERVAL_SECONDS",
        15
    )

    # --------------------------------------------------------
    # Temporal decay
    # --------------------------------------------------------

    decay: float = _float(
        "TEMPORAL_DECAY_MINUTES",
        60
    )

    # --------------------------------------------------------
    # Simulation speed
    # --------------------------------------------------------

    sim_speed: float = _float(
        "SIM_SPEED",
        2
    )

    # --------------------------------------------------------
    # Incident penalty
    # --------------------------------------------------------

    penalty_max: float = _float(
        "INCIDENT_PENALTY_MAX",
        50
    )


# ============================================================
# GLOBAL SETTINGS INSTANCE
# ============================================================

settings = Settings()