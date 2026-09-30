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

@dataclass
class Settings:
    # --------------------------------------------------------
    # OpenRouteService
    # --------------------------------------------------------

    ors_api_key: str = os.getenv("ORS_API_KEY", "").strip()

    # --------------------------------------------------------
    # Incident / route scoring
    # --------------------------------------------------------

    radius: float = _float("INCIDENT_ROUTE_RADIUS_METERS", 500)
    critical: float = _float("CRITICAL_SAFETY_THRESHOLD", 60)
    min_improve: float = _float("MIN_SAFETY_IMPROVEMENT", 15)
    max_extra: float = _float("MAX_EXTRA_TRAVEL_MINUTES", 10)
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() == "true"
    poll: int = _int("POLLING_INTERVAL_SECONDS", 15)
    decay: float = _float("TEMPORAL_DECAY_MINUTES", 60)
    sim_speed: float = _float("SIM_SPEED", 2)
    penalty_max: float = _float("INCIDENT_PENALTY_MAX", 50)
    location_update_interval_ms: int = _int("LOCATION_UPDATE_INTERVAL_MS", 15000)
    emergency_location_update_interval_ms: int = _int("EMERGENCY_LOCATION_UPDATE_INTERVAL_MS", 3000)
    safety_countdown_seconds: int = _int("SAFETY_COUNTDOWN_SECONDS", 10)
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

    # --------------------------------------------------------
    # SMTP (guardian alert emails); EMAIL_* names are accepted as fallbacks
    # --------------------------------------------------------

    smtp_host: str = os.getenv("SMTP_HOST") or os.getenv("EMAIL_HOST") or ""
    smtp_port: str = os.getenv("SMTP_PORT") or os.getenv("EMAIL_PORT") or ""
    smtp_username: str = os.getenv("SMTP_USERNAME") or os.getenv("EMAIL_USERNAME") or ""
    smtp_password: str = os.getenv("SMTP_PASSWORD") or os.getenv("EMAIL_PASSWORD") or ""
    smtp_from: str = os.getenv("SMTP_FROM") or os.getenv("EMAIL_FROM") or ""


# ============================================================
# SOS RISK SCORING
# ============================================================
#
# These values are authoritative; the design doc should match them.
# Keyword score: first match adds KEYWORD_FIRST_MATCH_SCORE, each repeat
# adds up to KEYWORD_REPEAT_SCORE until the keyword window reaches
# KEYWORD_WINDOW_CAP.

KEYWORD_FIRST_MATCH_SCORE = 40
KEYWORD_REPEAT_SCORE = 25
KEYWORD_WINDOW_CAP = 70
EMOTION_ANGRY_SCORE = 25
EMOTION_SAD_SCORE = 10


# ============================================================
# GLOBAL SETTINGS INSTANCE
# ============================================================

settings = Settings()