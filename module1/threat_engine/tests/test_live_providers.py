"""Open-Meteo and Overpass stay in 0..1 and fail closed."""

import httpx
import pytest

from app import config
from app.explain import ExplainContext, explain
from app.providers import safe_places, weather
from app.providers.safe_places import haversine_m
from app.schemas import AssessRequest, Contributor

SAMPLE = AssessRequest.model_validate(
    {
        "session_id": "abc",
        "timestamp": "2026-09-29T23:40:00+05:30",
        "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
    }
)


@pytest.fixture
def live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MOCK_MODE", False)


@pytest.mark.parametrize("code", [0, 3, 45, 61, 71, 95, 999])
def test_weather_codes_stay_in_range(code: int) -> None:
    risk, _reason = weather.risk_for_code(code)
    assert 0.0 <= risk <= 1.0


def test_storm_rain_and_fog_raise_risk_above_clear() -> None:
    clear, _clear_reason = weather.risk_for_code(0)
    fog, _fog_reason = weather.risk_for_code(45)
    rain, _rain_reason = weather.risk_for_code(61)
    storm, _storm_reason = weather.risk_for_code(95)
    assert clear < fog
    assert clear < rain
    assert rain < storm


def test_weather_timeout_and_bad_payload_are_unavailable(
    live_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _timeout(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(weather, "fetch_weather_payload", _timeout)
    timed_out = weather.signal(SAMPLE)
    assert timed_out.available is False
    assert 0.0 <= timed_out.risk <= 1.0

    def _bad(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        return {"unexpected": True}

    monkeypatch.setattr(weather, "fetch_weather_payload", _bad)
    bad = weather.signal(SAMPLE)
    assert bad.available is False
    assert 0.0 <= bad.risk <= 1.0


def test_weather_live_payload_is_cached(
    live_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def _ok(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        calls["count"] += 1
        return {"current": {"weather_code": 61}}

    monkeypatch.setattr(weather, "fetch_weather_payload", _ok)
    first = weather.signal(SAMPLE)
    second = weather.signal(SAMPLE)
    assert first.available is True
    assert first.risk == pytest.approx(config.WEATHER_RAIN_RISK)
    assert second.risk == first.risk
    assert calls["count"] == 1
    assert weather._CACHE.ttl == config.WEATHER_CACHE_TTL_SECONDS


def test_safe_place_live_payload_includes_name_distance_and_direction(
    live_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    place_lon = SAMPLE.location.lon + 0.002

    def _ok(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        return {
            "elements": [
                {
                    "type": "node",
                    "lat": SAMPLE.location.lat,
                    "lon": place_lon,
                    "tags": {"amenity": "hospital", "name": "City Hospital"},
                }
            ]
        }

    monkeypatch.setattr(safe_places, "fetch_overpass_payload", _ok)
    result = safe_places.signal(SAMPLE)
    distance = haversine_m(SAMPLE.location.lat, SAMPLE.location.lon, SAMPLE.location.lat, place_lon)
    assert result.available is True
    assert 0.0 <= result.risk <= 1.0
    assert result.risk == pytest.approx(distance / config.SAFE_PLACES_RISK_DISTANCE_M)
    assert result.details["label"] == "City Hospital"
    assert result.details["direction"] == "east"
    assert result.details["distance_m"] == pytest.approx(distance)
    _explanation, recommendations = explain(
        40,
        [Contributor(signal="safe_places", points=4, reason=result.reason)],
        ExplainContext(
            safe_distance_m=distance,
            safe_place_name="City Hospital",
            safe_place_direction="east",
        ),
    )
    assert any(item == f"City Hospital is about {round(distance)} m east." for item in recommendations)


def test_safe_place_timeout_and_bad_payload_are_unavailable(
    live_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _timeout(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(safe_places, "fetch_overpass_payload", _timeout)
    timed_out = safe_places.signal(SAMPLE)
    assert timed_out.available is False
    assert 0.0 <= timed_out.risk <= 1.0

    def _bad(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        return {"remark": "runtime error"}

    monkeypatch.setattr(safe_places, "fetch_overpass_payload", _bad)
    bad = safe_places.signal(SAMPLE)
    assert bad.available is False
    assert 0.0 <= bad.risk <= 1.0


def test_safe_place_cache_is_one_kilometer(
    live_mode: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def _ok(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        calls["count"] += 1
        return {
            "elements": [
                {
                    "type": "node",
                    "lat": lat,
                    "lon": lon + 0.001,
                    "tags": {"amenity": "police", "name": "Local Police"},
                }
            ]
        }

    monkeypatch.setattr(safe_places, "fetch_overpass_payload", _ok)
    safe_places.signal(SAMPLE)
    nearby = SAMPLE.model_copy(
        update={"location": SAMPLE.location.model_copy(update={"lat": SAMPLE.location.lat + 0.002})}
    )
    safe_places.signal(nearby)
    assert calls["count"] == 1
    assert config.SAFE_PLACES_CACHE_CELL_M == 1000
    assert safe_places._CACHE.ttl == config.OVERPASS_CACHE_TTL_SECONDS


def test_mock_mode_does_not_call_live_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        raise AssertionError("live client should not be called")

    monkeypatch.setattr(config, "MOCK_MODE", True)
    monkeypatch.setattr(weather, "fetch_weather_payload", _boom)
    monkeypatch.setattr(safe_places, "fetch_overpass_payload", _boom)
    assert weather.signal(SAMPLE).available is True
    assert safe_places.signal(SAMPLE).available is True
    assert weather.signal(SAMPLE).reason == "mock weather is clear"
