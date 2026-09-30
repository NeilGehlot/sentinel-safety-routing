"""Horizon projection. Position follows speed and time. Scores stay offline in mock mode."""

import pytest

from app import config
from app.engine import assess
from app.prediction import decay_battery, project_position
from app.providers import safe_places, weather
from app.providers.safe_places import haversine_m
from app.schemas import AssessRequest

ORIGIN_LAT = 28.4595
ORIGIN_LON = 77.0266

SAMPLE = {
    "session_id": "abc",
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {
        "lat": ORIGIN_LAT,
        "lon": ORIGIN_LON,
        "speed_mps": 1.4,
        "heading_deg": 90,
    },
    "device": {"battery_pct": 18, "cellular_dbm": -108, "internet_available": False},
    "nearby_devices": {"ble_count": 3, "wifi_count": 2},
    "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
}


def test_stationary_user_keeps_the_same_position() -> None:
    for horizon in config.PREDICTION_HORIZONS_MIN:
        assert project_position(ORIGIN_LAT, ORIGIN_LON, 0.0, 90, horizon) == (ORIGIN_LAT, ORIGIN_LON)
        assert project_position(ORIGIN_LAT, ORIGIN_LON, 0.29, 180, horizon) == (ORIGIN_LAT, ORIGIN_LON)
        assert project_position(ORIGIN_LAT, ORIGIN_LON, None, 90, horizon) == (ORIGIN_LAT, ORIGIN_LON)


def test_moving_distance_matches_speed_times_time() -> None:
    speed_mps = 1.4
    for horizon in config.PREDICTION_HORIZONS_MIN:
        lat, lon = project_position(ORIGIN_LAT, ORIGIN_LON, speed_mps, 90, horizon)
        distance_m = haversine_m(ORIGIN_LAT, ORIGIN_LON, lat, lon)
        expected_m = speed_mps * horizon * 60
        assert distance_m == pytest.approx(expected_m, rel=1e-4)
        assert lon > ORIGIN_LON


def test_battery_drops_one_percent_per_five_minutes() -> None:
    assert decay_battery(18, 5) == pytest.approx(17)
    assert decay_battery(18, 10) == pytest.approx(16)
    assert decay_battery(0.4, 10) == 0.0


@pytest.mark.asyncio
async def test_response_includes_both_horizons_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(lat: float, lon: float) -> dict[str, object]:
        _ = (lat, lon)
        raise AssertionError("projected re-score called a live client")

    monkeypatch.setattr(config, "MOCK_MODE", True)
    monkeypatch.setattr(weather, "fetch_weather_payload", _boom)
    monkeypatch.setattr(safe_places, "fetch_overpass_payload", _boom)
    response = await assess(AssessRequest.model_validate(SAMPLE))
    assert [item.horizon_min for item in response.predicted] == [5, 10]
    for item in response.predicted:
        assert 0 <= item.score <= 100
        dumped = item.model_dump()
        assert set(dumped) == {"horizon_min", "score"}
