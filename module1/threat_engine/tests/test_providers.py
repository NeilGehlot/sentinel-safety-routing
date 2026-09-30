"""Each provider stays in 0..1 and returns unavailable on missing data."""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import (
    MOCK_WEATHER_RISK,
    MOVEMENT_RISK,
    NEARBY_FEW_NIGHT_RISK,
    NEARBY_MANY_RISK,
    NEARBY_SPIKE_BUMP,
    TIME_LOW_RISK,
    TIME_PEAK_RISK,
)
from app.engine import collect_signals
from app.news_retrieve import wire_retrieve
from app.providers import (
    cellular,
    connectivity,
    crime_risk,
    crowd_density,
    gps_context,
    movement,
    nearby_devices,
    news_risk,
    safe_places,
    time_of_day,
    weather,
)
from app.providers.base import PreviousObservation, SignalResult
from app.schemas import AssessRequest, DeviceState, Location, Movement, NearbyDevices

IST = timezone(timedelta(hours=5, minutes=30))
SAMPLE = AssessRequest.model_validate(
    {
        "session_id": "abc",
        "timestamp": "2026-09-29T23:40:00+05:30",
        "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
        "device": {"battery_pct": 18, "cellular_dbm": -108, "internet_available": False},
        "nearby_devices": {"ble_count": 3, "wifi_count": 2},
        "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
    }
)


def _at(hour: int, minute: int = 0) -> AssessRequest:
    return SAMPLE.model_copy(
        update={"timestamp": datetime(2026, 9, 29, hour, minute, tzinfo=IST)}
    )


def test_collect_signals_stay_in_range_and_cover_every_provider() -> None:
    signals = collect_signals(SAMPLE, None)
    names = {item.name for item in signals}
    assert names == {
        "gps",
        "time_of_day",
        "weather",
        "crime_risk",
        "news_risk",
        "crowd_density",
        "cellular",
        "connectivity_battery",
        "connectivity_internet",
        "safe_places",
        "nearby_devices",
        "movement",
    }
    for item in signals:
        assert 0.0 <= item.risk <= 1.0
        assert item.available is True


def test_gps_is_context_only() -> None:
    result = gps_context.signal(SAMPLE)
    assert result.available is True
    assert result.risk == 0.0
    assert result.details["lat"] == 28.4595
    assert result.details["speed_mps"] == 1.4
    missing = AssessRequest.model_construct(timestamp=SAMPLE.timestamp, location=None)
    assert gps_context.signal(missing).available is False


def test_time_of_day_low_band_and_peak_band() -> None:
    noon = time_of_day.signal(_at(12))
    peak = time_of_day.signal(_at(2))
    assert noon.risk == pytest.approx(TIME_LOW_RISK)
    assert peak.risk == pytest.approx(TIME_PEAK_RISK)
    assert peak.risk > noon.risk
    missing = AssessRequest.model_construct(timestamp=None, location=SAMPLE.location)
    assert time_of_day.signal(missing).available is False


def test_weather_uses_the_mock_risk() -> None:
    result = weather.signal(SAMPLE)
    assert result.available is True
    assert result.risk == pytest.approx(MOCK_WEATHER_RISK)
    missing = AssessRequest.model_construct(timestamp=SAMPLE.timestamp, location=None)
    assert weather.signal(missing).available is False


def test_crime_grid_lookup_and_missing_cell() -> None:
    found = crime_risk.signal(SAMPLE)
    assert found.available is True
    assert found.risk == pytest.approx(0.82)
    missing_cell = SAMPLE.model_copy(update={"location": Location(lat=1.0, lon=1.0)})
    missed = crime_risk.signal(missing_cell)
    assert missed.available is False
    assert 0.0 <= missed.risk <= 1.0
    broken = AssessRequest.model_construct(timestamp=SAMPLE.timestamp, location=None)
    assert crime_risk.signal(broken).available is False


def test_crime_grid_missing_file_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crime_risk, "CRIME_GRID_PATH", "missing-crime-grid.csv")
    result = crime_risk.signal(SAMPLE)
    assert result.available is False


def test_news_stub_severity_and_failed_retrieve() -> None:
    result = news_risk.signal(SAMPLE)
    assert result.available is True
    assert 0.0 <= result.risk <= 1.0
    assert result.risk > 0.0

    def _boom(lat: float, lon: float, radius_m: float, hours: float) -> None:
        _ = (lat, lon, radius_m, hours)
        raise RuntimeError("retrieve failed")

    wire_retrieve(_boom)
    failed = news_risk.signal(SAMPLE)
    assert failed.available is False

    wire_retrieve(lambda lat, lon, radius_m, hours: [])
    empty = news_risk.signal(SAMPLE)
    assert empty.available is True
    assert empty.risk == 0.0


def test_crowd_density_is_higher_at_night_than_at_noon() -> None:
    night = crowd_density.signal(_at(23, 40))
    day = crowd_density.signal(_at(12))
    assert night.available is True and day.available is True
    assert night.risk > day.risk
    assert 0.0 <= night.risk <= 1.0
    missing = AssessRequest.model_construct(timestamp=None, location=None)
    assert crowd_density.signal(missing).available is False


def test_cellular_weak_signal_raises_risk() -> None:
    weak = cellular.signal(SAMPLE)
    strong = SAMPLE.model_copy(
        update={"device": DeviceState(battery_pct=80, cellular_dbm=-60, internet_available=True)}
    )
    strong_result = cellular.signal(strong)
    assert weak.risk > 0.5
    assert strong_result.risk == 0.0
    assert cellular.signal(SAMPLE.model_copy(update={"device": None})).available is False


def test_connectivity_battery_and_internet_are_separate() -> None:
    battery, internet = connectivity.signals(SAMPLE)
    assert battery.name == "connectivity_battery"
    assert internet.name == "connectivity_internet"
    assert battery.risk > 0.0
    assert internet.risk == 1.0
    charged = SAMPLE.model_copy(
        update={"device": DeviceState(battery_pct=80, cellular_dbm=-80, internet_available=True)}
    )
    ok_battery, ok_internet = connectivity.signals(charged)
    assert ok_battery.risk == 0.0
    assert ok_internet.risk == 0.0
    critical = SAMPLE.model_copy(
        update={"device": DeviceState(battery_pct=5, cellular_dbm=-80, internet_available=True)}
    )
    low_battery, _internet = connectivity.signals(critical)
    assert low_battery.risk > battery.risk
    missing = connectivity.signals(SAMPLE.model_copy(update={"device": None}))
    assert [item.available for item in missing] == [False, False]


def test_safe_place_risk_is_distance_over_1500() -> None:
    result = safe_places.signal(SAMPLE)
    assert result.available is True
    assert result.risk == pytest.approx(800 / 1500)
    assert result.details["distance_m"] == 800
    missing = AssessRequest.model_construct(timestamp=SAMPLE.timestamp, location=None)
    assert safe_places.signal(missing).available is False


def test_nearby_few_at_night_and_small_spike() -> None:
    night = nearby_devices.signal(_at(23, 40))
    day = nearby_devices.signal(_at(12))
    assert night.risk == pytest.approx(NEARBY_FEW_NIGHT_RISK)
    assert day.risk < night.risk
    many = _at(23, 40).model_copy(
        update={"nearby_devices": NearbyDevices(ble_count=40, wifi_count=10)}
    )
    many_result = nearby_devices.signal(many)
    assert many_result.risk == pytest.approx(NEARBY_MANY_RISK)
    assert many_result.risk < night.risk
    spiked = nearby_devices.signal(many, PreviousObservation(nearby_total=2))
    assert spiked.risk == pytest.approx(many_result.risk + NEARBY_SPIKE_BUMP)
    assert spiked.risk < night.risk
    assert nearby_devices.signal(SAMPLE.model_copy(update={"nearby_devices": None})).available is False


def test_movement_activity_window_and_missing() -> None:
    walking = SAMPLE.model_copy(update={"movement": Movement(activity="walking")})
    running = SAMPLE.model_copy(update={"movement": Movement(activity="running")})
    window = movement.signal(SAMPLE)
    assert movement.signal(walking).risk == pytest.approx(MOVEMENT_RISK["walking"])
    assert movement.signal(running).risk == pytest.approx(MOVEMENT_RISK["running"])
    assert window.risk == pytest.approx(MOVEMENT_RISK["stationary"])
    assert window.details["activity"] == "stationary"
    assert movement.signal(SAMPLE.model_copy(update={"movement": None})).available is False
    stopped = movement.signal(
        SAMPLE.model_copy(update={"location": Location(lat=28.45, lon=77.02, speed_mps=0.0)}),
        previous_speed=2.0,
        previous_at=SAMPLE.timestamp - timedelta(seconds=30),
    )
    assert stopped.details["activity"] == "sudden_stop"
    assert stopped.risk == pytest.approx(MOVEMENT_RISK["sudden_stop"])


def test_provider_results_are_signal_results() -> None:
    result = time_of_day.signal(SAMPLE)
    assert isinstance(result, SignalResult)
