"""Centralised, env-driven configuration (all thresholds live here)."""
import os
from dataclasses import dataclass

def _f(k, d): return float(os.getenv(k, d))

@dataclass
class Settings:
    ors_api_key: str = os.getenv("ORS_API_KEY", "")
    radius: float = _f("INCIDENT_ROUTE_RADIUS_METERS", 500)
    critical: float = _f("CRITICAL_SAFETY_THRESHOLD", 60)
    min_improve: float = _f("MIN_SAFETY_IMPROVEMENT", 15)
    max_extra: float = _f("MAX_EXTRA_TRAVEL_MINUTES", 10)
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() == "true"
    poll: int = int(os.getenv("POLLING_INTERVAL_SECONDS", 15))
    decay: float = _f("TEMPORAL_DECAY_MINUTES", 60)   # prototype relevance model, not a clearance predictor
    sim_speed: float = _f("SIM_SPEED", 2)              # demo: journey moves faster than real time
    penalty_max: float = _f("INCIDENT_PENALTY_MAX", 50)
    location_update_interval_ms: int = int(os.getenv("LOCATION_UPDATE_INTERVAL_MS", 15000))
    emergency_location_update_interval_ms: int = int(os.getenv("EMERGENCY_LOCATION_UPDATE_INTERVAL_MS", 3000))
    safety_countdown_seconds: int = int(os.getenv("SAFETY_COUNTDOWN_SECONDS", 10))
    escalation_delay_seconds: int = int(os.getenv("ESCALATION_DELAY_SECONDS", 30))
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

settings = Settings()
