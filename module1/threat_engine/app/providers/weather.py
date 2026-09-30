"""Weather risk. Mock mode stays offline. Otherwise this calls Open-Meteo.

Rain, fog, and storm raise risk. Results are cached for 30 minutes.
A timeout or a bad payload returns available=False and does not raise.
"""

from cachetools import TTLCache
import httpx

from app import config
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest

_CACHE: TTLCache[tuple[float, float], int] = TTLCache(
    maxsize=128,
    ttl=config.WEATHER_CACHE_TTL_SECONDS,
)


def clear_cache() -> None:
    """Drop cached forecast codes. Tests use this so calls do not leak."""
    _CACHE.clear()


def risk_for_code(code: int) -> tuple[float, str]:
    """Map a WMO weather code to risk. Rain, fog, and storm sit above clear."""
    if code in config.WEATHER_STORM_CODES:
        return config.WEATHER_STORM_RISK, "weather is stormy"
    if code in config.WEATHER_FOG_CODES:
        return config.WEATHER_FOG_RISK, "weather is foggy"
    if code in config.WEATHER_RAIN_CODES:
        return config.WEATHER_RAIN_RISK, "weather is rainy"
    if code in config.WEATHER_SNOW_CODES:
        return config.WEATHER_SNOW_RISK, "weather is snowy"
    if code in config.WEATHER_CLOUD_CODES:
        return config.WEATHER_CLOUD_RISK, "weather is cloudy"
    if code == 0:
        return config.WEATHER_CLEAR_RISK, "weather is clear"
    return config.WEATHER_UNKNOWN_RISK, "weather code is unrecognized"


def fetch_weather_payload(lat: float, lon: float) -> dict[str, object]:
    """GET the current weather code. Raises on timeout, HTTP errors, or bad JSON."""
    params = {"latitude": lat, "longitude": lon, "current": "weather_code"}
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept": "application/json"}
    timeout = httpx.Timeout(config.WEATHER_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.get(config.OPEN_METEO_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Weather payload was not an object.")
    return payload


def _code_from_payload(payload: dict[str, object]) -> int:
    current = payload.get("current")
    if not isinstance(current, dict) or "weather_code" not in current:
        raise ValueError("Weather payload has no weather code.")
    return int(current["weather_code"])


def _live_code(lat: float, lon: float) -> tuple[int | None, str]:
    key = (round(lat, config.WEATHER_CACHE_DECIMALS), round(lon, config.WEATHER_CACHE_DECIMALS))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached, ""
    try:
        code = _code_from_payload(fetch_weather_payload(lat, lon))
    except httpx.TimeoutException:
        return None, "Weather forecast timed out."
    except Exception:
        return None, "Weather forecast payload was not usable."
    _CACHE[key] = code
    return code, ""


def _mock(lat: float, lon: float) -> SignalResult:
    return SignalResult(
        name="weather",
        risk=clamp_risk(config.MOCK_WEATHER_RISK),
        reason="mock weather is clear",
        available=True,
        details={"lat": lat, "lon": lon},
    )


def signal(request: AssessRequest) -> SignalResult:
    """Mock when MOCK_MODE is on. Otherwise read Open-Meteo and never raise."""
    try:
        location = request.location
        if location is None:
            return unavailable("weather", "Location is missing.")
        if config.MOCK_MODE:
            return _mock(location.lat, location.lon)
        code, error = _live_code(location.lat, location.lon)
        if code is None:
            return unavailable("weather", error or "Weather forecast could not be read.")
        risk, reason = risk_for_code(code)
        return SignalResult(
            name="weather",
            risk=clamp_risk(risk),
            reason=reason,
            available=True,
            details={"lat": location.lat, "lon": location.lon, "weather_code": float(code)},
        )
    except Exception:
        return unavailable("weather", "Weather could not be read.")
