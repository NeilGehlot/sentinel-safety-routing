"""Environment, weights, and scoring thresholds.

Numeric rules live here so provider and scoring logic does not hardcode them.
"""

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


MOCK_MODE: bool = _as_bool(os.getenv("MOCK_MODE", "true"))
OPEN_METEO_URL: str = os.getenv(
    "OPEN_METEO_URL",
    "https://api.open-meteo.com/v1/forecast",
)
OVERPASS_URL: str = os.getenv(
    "OVERPASS_URL",
    "https://overpass-api.de/api/interpreter",
)
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT_SECONDS: float = 8.0
LLM_MAX_TOKENS: int = 200
USE_LLM: bool = _as_bool(os.getenv("USE_LLM", "false"))
CRIME_GRID_PATH: str = os.getenv("CRIME_GRID_PATH", "app/data/crime_grid.csv")

SCORE_MIN: int = 0
SCORE_MAX: int = 100
SIGNAL_RISK_MIN: float = 0.0
SIGNAL_RISK_MAX: float = 1.0

# Section 6. GPS is an input, not a scored signal. Weights sum to 100.
POSITIVE_WEIGHTS: dict[str, int] = {
    "crime_risk": 13,
    "news_risk": 8,
    "time_of_day": 12,
    "crowd_density": 8,
    "safe_places": 8,
    "nearby_devices": 8,
    "cellular": 14,
    "internet": 4,
    "battery": 10,
    "weather": 3,
    "movement": 12,
    "gps": 0,
}

# Section 8. Safe-place risk is distance / this many meters, clamped to 0..1.
SAFE_PLACES_RISK_DISTANCE_M: float = 1500.0
SAFE_PLACES_CLOSE_DISTANCE_M: int = 300
SAFE_PLACES_CLOSE_POINTS: int = -8
MOCK_SAFE_PLACE_DISTANCE_M: float = 800.0
MOCK_SAFE_PLACE_LABEL: str = "nearest safe place"

# Time of day. Low band is 07:00-19:00. Peak band is 00:00-04:00.
# Hours outside those bands ramp linearly between the two risks.
TIME_LOW_START_HOUR: float = 7.0
TIME_LOW_END_HOUR: float = 19.0
TIME_PEAK_START_HOUR: float = 0.0
TIME_PEAK_END_HOUR: float = 4.0
TIME_LOW_RISK: float = 0.1
TIME_PEAK_RISK: float = 1.0

# Weather. Mock mode uses MOCK_WEATHER_RISK. Live mode calls Open-Meteo.
MOCK_WEATHER_RISK: float = 0.2
WEATHER_TIMEOUT_SECONDS: float = 8.0
WEATHER_CACHE_TTL_SECONDS: int = 1800
WEATHER_CACHE_DECIMALS: int = 2
WEATHER_CLEAR_RISK: float = 0.1
WEATHER_CLOUD_RISK: float = 0.2
WEATHER_FOG_RISK: float = 0.55
WEATHER_RAIN_RISK: float = 0.7
WEATHER_SNOW_RISK: float = 0.7
WEATHER_STORM_RISK: float = 0.95
WEATHER_UNKNOWN_RISK: float = 0.2
WEATHER_CLOUD_CODES: tuple[int, ...] = (1, 2, 3)
WEATHER_FOG_CODES: tuple[int, ...] = (45, 48)
WEATHER_RAIN_CODES: tuple[int, ...] = (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82)
WEATHER_SNOW_CODES: tuple[int, ...] = (71, 73, 75, 77, 85, 86)
WEATHER_STORM_CODES: tuple[int, ...] = (95, 96, 99)
HTTP_USER_AGENT: str = "threat-engine/0.1"

# Safe places. Mock mode uses the fixed distance. Live mode calls Overpass.
OVERPASS_TIMEOUT_SECONDS: float = 20.0
OVERPASS_QUERY_TIMEOUT_SECONDS: int = 15
OVERPASS_CACHE_TTL_SECONDS: int = 1800
SAFE_PLACES_CACHE_CELL_M: int = 1000
OVERPASS_SEARCH_RADIUS_M: int = 2000
EARTH_RADIUS_M: float = 6371000.0

# Synthetic crime grid.
CRIME_GRID_BIN_DEG: float = 0.01
CRIME_GRID_CACHE_TTL_SECONDS: int = 300
DEFAULT_CRIME_GRID_PATH: str = "app/data/crime_grid.csv"
# LightGBM crime model. The grid above is the fallback when this artifact is missing.
_CRIME_ARTIFACTS = Path(__file__).resolve().parents[1] / "ml" / "artifacts"
CRIME_MODEL_PATH: str = os.getenv("CRIME_MODEL_PATH", str(_CRIME_ARTIFACTS / "crime_risk.txt"))
CRIME_MODEL_META_PATH: str = os.getenv(
    "CRIME_MODEL_META_PATH",
    str(_CRIME_ARTIFACTS / "crime_risk_meta.json"),
)
CRIME_MODEL_BIN_DEG: float = 0.05
CRIME_MODEL_MIN_CELL_INCIDENTS: int = 50
CRIME_MODEL_TEST_YEAR: int = 2024
CRIME_MODEL_SPATIAL_LAT_QUANTILE: float = 0.8
OSM_FEATURE_TIMEOUT_SECONDS: float = 20.0

# Movement classifier. The rule-based provider is the fallback when this artifact is missing.
MOTION_MODEL_PATH: str = os.getenv("MOTION_MODEL_PATH", str(_CRIME_ARTIFACTS / "motion.joblib"))
MOTION_MODEL_META_PATH: str = os.getenv(
    "MOTION_MODEL_META_PATH",
    str(_CRIME_ARTIFACTS / "motion_meta.json"),
)

# News stub. Severity is already on a 0..1 scale.
NEWS_RADIUS_M: int = 1000
NEWS_LOOKBACK_HOURS: int = 48
NEWS_MOCK_SEVERITY: float = 0.45

# Crowd density is a place-density proxy adjusted by time of day.
MOCK_PLACE_DENSITY: float = 0.25
CROWD_DAY_MULTIPLIER: float = 0.4
CROWD_NIGHT_MULTIPLIER: float = 1.0

# Cellular signal. risk = clamp((-70 - dBm) / 55, 0, 1). No history.
CELLULAR_STRONG_DBM: float = -70.0
CELLULAR_WEAK_DBM: float = -125.0
CELLULAR_ADVISORY_DBM: float = -100.0

# Connectivity: battery and internet are separate signals.
BATTERY_LOW_PCT: float = 20.0
BATTERY_CRITICAL_PCT: float = 10.0
BATTERY_OK_RISK: float = 0.0
BATTERY_LOW_RISK: float = 0.55
BATTERY_CRITICAL_RISK: float = 1.0
INTERNET_AVAILABLE_RISK: float = 0.0
INTERNET_UNAVAILABLE_RISK: float = 1.0

# Nearby devices. A high count is not danger. The spike bump stays small.
# Curve knots are (combined count, risk). Demo chips land on 0, 8, 23, and 60.
NEARBY_FEW_MAX_COUNT: int = 5
NEARBY_MANY_MIN_COUNT: int = 25
NEARBY_FEW_NIGHT_RISK: float = 0.8
NEARBY_FEW_DAY_RISK: float = 0.2
NEARBY_TYPICAL_RISK: float = 0.15
NEARBY_MANY_RISK: float = 0.05
NEARBY_CURVE: tuple[tuple[int, float], ...] = (
    (0, 1.0),
    (8, 0.65),
    (23, 0.32),
    (60, 0.0),
)
NEARBY_SPIKE_MIN_INCREASE: int = 10
NEARBY_SPIKE_BUMP: float = 0.1

# Movement. sudden_stop is derived from speed change, not a request activity.
MOVEMENT_RISK: dict[str, float] = {
    "stationary": 0.15,
    "walking": 0.15,
    "vehicle": 0.3,
    "running": 0.85,
    "fall": 1.0,
    "sudden_stop": 0.9,
}
ACCEL_FALL_MAGNITUDE_MPS2: float = 25.0
ACCEL_RUNNING_STDEV_MPS2: float = 3.0
SUDDEN_STOP_PREV_MIN_SPEED_MPS: float = 1.0
SUDDEN_STOP_MAX_GAP_SECONDS: int = 180

# Explanation wording only. These cuts do not change the numeric score.
SUMMARY_ELEVATED_AT: int = 30
SUMMARY_HIGH_AT: int = 60
MAX_RECOMMENDATIONS: int = 3

# Section 9. Applied by the later prediction phase.
PREDICTION_HORIZONS_MIN: tuple[int, ...] = (5, 10)
STATIONARY_SPEED_MPS: float = 0.3
BATTERY_DECAY_PERCENT_PER_5_MIN: int = 1
BATTERY_DECAY_INTERVAL_MIN: int = 5


@dataclass(frozen=True)
class RiskGreaterThan:
    """A signal risk must be strictly greater than the threshold."""

    signal: str
    threshold: float


@dataclass(frozen=True)
class InteractionRule:
    """Fixed points added when every condition holds."""

    name: str
    points: int
    risk_greater_than: tuple[RiskGreaterThan, ...]
    movement: tuple[str, ...] = ()


INTERACTION_RULES: tuple[InteractionRule, ...] = (
    InteractionRule(
        name="isolated_night",
        points=10,
        risk_greater_than=(
            RiskGreaterThan("time_of_day", 0.7),
            RiskGreaterThan("crowd_density", 0.7),
            RiskGreaterThan("cellular", 0.5),
        ),
    ),
    InteractionRule(
        name="distress_movement",
        points=10,
        risk_greater_than=(RiskGreaterThan("crowd_density", 0.6),),
        movement=("running", "fall", "sudden_stop"),
    ),
)


def _validate_config() -> None:
    total = sum(POSITIVE_WEIGHTS.values())
    if total != SCORE_MAX:
        raise RuntimeError(f"Signal weights must sum to {SCORE_MAX}, got {total}.")
    if POSITIVE_WEIGHTS.get("gps") != 0:
        raise RuntimeError("GPS weight must be 0.")
    if SAFE_PLACES_CLOSE_DISTANCE_M <= 0:
        raise RuntimeError("Safe place distance must be positive.")
    if not PREDICTION_HORIZONS_MIN or any(item <= 0 for item in PREDICTION_HORIZONS_MIN):
        raise RuntimeError("Prediction horizons must be positive.")
    if STATIONARY_SPEED_MPS < 0:
        raise RuntimeError("Stationary speed cannot be negative.")
    if BATTERY_DECAY_INTERVAL_MIN <= 0 or BATTERY_DECAY_PERCENT_PER_5_MIN < 0:
        raise RuntimeError("Battery decay settings are invalid.")
    if SAFE_PLACES_RISK_DISTANCE_M <= 0:
        raise RuntimeError("Safe place risk distance must be positive.")
    if not (0 <= TIME_PEAK_START_HOUR < TIME_PEAK_END_HOUR < TIME_LOW_START_HOUR < TIME_LOW_END_HOUR <= 24):
        raise RuntimeError("Time of day bands are out of order.")
    if not (0 <= TIME_LOW_RISK <= TIME_PEAK_RISK <= 1):
        raise RuntimeError("Time of day risks must sit between 0 and 1.")
    _unit_risks = (
        MOCK_WEATHER_RISK,
        WEATHER_CLEAR_RISK,
        WEATHER_CLOUD_RISK,
        WEATHER_FOG_RISK,
        WEATHER_RAIN_RISK,
        WEATHER_SNOW_RISK,
        WEATHER_STORM_RISK,
        WEATHER_UNKNOWN_RISK,
        NEWS_MOCK_SEVERITY,
        MOCK_PLACE_DENSITY,
        CROWD_DAY_MULTIPLIER,
        CROWD_NIGHT_MULTIPLIER,
        BATTERY_OK_RISK,
        BATTERY_LOW_RISK,
        BATTERY_CRITICAL_RISK,
        INTERNET_AVAILABLE_RISK,
        INTERNET_UNAVAILABLE_RISK,
        NEARBY_FEW_NIGHT_RISK,
        NEARBY_FEW_DAY_RISK,
        NEARBY_TYPICAL_RISK,
        NEARBY_MANY_RISK,
        NEARBY_SPIKE_BUMP,
        *MOVEMENT_RISK.values(),
    )
    if any(item < 0 or item > 1 for item in _unit_risks):
        raise RuntimeError("Configured risks must sit between 0 and 1.")
    if not (0 < BATTERY_CRITICAL_PCT < BATTERY_LOW_PCT <= 100):
        raise RuntimeError("Battery thresholds are out of order.")
    if CELLULAR_WEAK_DBM >= CELLULAR_STRONG_DBM:
        raise RuntimeError("Cellular weak dBm must be below the strong dBm.")
    if CRIME_GRID_BIN_DEG <= 0 or CRIME_GRID_CACHE_TTL_SECONDS <= 0:
        raise RuntimeError("Crime grid settings are invalid.")
    if CRIME_MODEL_BIN_DEG <= 0 or CRIME_MODEL_MIN_CELL_INCIDENTS < 1:
        raise RuntimeError("Crime model grid settings are invalid.")
    if not 2000 <= CRIME_MODEL_TEST_YEAR <= 2100:
        raise RuntimeError("Crime model test year is invalid.")
    if not 0 < CRIME_MODEL_SPATIAL_LAT_QUANTILE < 1:
        raise RuntimeError("Spatial holdout quantile must sit between 0 and 1.")
    if OSM_FEATURE_TIMEOUT_SECONDS <= 0:
        raise RuntimeError("OSM feature timeout must be positive.")
    if NEWS_RADIUS_M <= 0 or NEWS_LOOKBACK_HOURS <= 0:
        raise RuntimeError("News lookup settings are invalid.")
    if LLM_TIMEOUT_SECONDS <= 0 or LLM_MAX_TOKENS < 1:
        raise RuntimeError("LLM timeout and token cap must be positive.")
    if NEARBY_FEW_MAX_COUNT < 0 or NEARBY_MANY_MIN_COUNT <= NEARBY_FEW_MAX_COUNT:
        raise RuntimeError("Nearby device counts are out of order.")
    if SUDDEN_STOP_PREV_MIN_SPEED_MPS < 0 or SUDDEN_STOP_MAX_GAP_SECONDS <= 0:
        raise RuntimeError("Sudden stop settings are invalid.")
    if MAX_RECOMMENDATIONS < 1:
        raise RuntimeError("At least one recommendation slot is required.")
    if WEATHER_TIMEOUT_SECONDS <= 0 or WEATHER_CACHE_TTL_SECONDS <= 0:
        raise RuntimeError("Weather timeout and cache must be positive.")
    if WEATHER_CACHE_TTL_SECONDS != 1800:
        raise RuntimeError("Weather cache must be 30 minutes.")
    if OVERPASS_TIMEOUT_SECONDS <= 0 or OVERPASS_CACHE_TTL_SECONDS <= 0:
        raise RuntimeError("Overpass timeout and cache must be positive.")
    if SAFE_PLACES_CACHE_CELL_M != 1000:
        raise RuntimeError("Safe place cache cell must be 1 km.")
    if OVERPASS_SEARCH_RADIUS_M <= 0 or EARTH_RADIUS_M <= 0:
        raise RuntimeError("Safe place search settings are invalid.")
    if not (WEATHER_CLEAR_RISK < WEATHER_FOG_RISK <= WEATHER_RAIN_RISK < WEATHER_STORM_RISK):
        raise RuntimeError("Weather risks must rise from clear to storm.")


_validate_config()
