"""Section 6 weights and the section 8 and 9 constants live in config only."""

from app.config import (
    BATTERY_DECAY_INTERVAL_MIN,
    BATTERY_DECAY_PERCENT_PER_5_MIN,
    INTERACTION_RULES,
    POSITIVE_WEIGHTS,
    PREDICTION_HORIZONS_MIN,
    SAFE_PLACES_CLOSE_DISTANCE_M,
    SAFE_PLACES_CLOSE_POINTS,
    SAFE_PLACES_RISK_DISTANCE_M,
    STATIONARY_SPEED_MPS,
)


def test_weights_match_spec_and_sum_to_100() -> None:
    assert POSITIVE_WEIGHTS == {
        "time_of_day": 12,
        "weather": 6,
        "crime_risk": 18,
        "news_risk": 12,
        "crowd_density": 8,
        "cellular": 10,
        "connectivity_battery": 4,
        "connectivity_internet": 4,
        "safe_places": 8,
        "nearby_devices": 6,
        "movement": 12,
        "gps": 0,
    }
    assert sum(POSITIVE_WEIGHTS.values()) == 100


def test_later_phase_thresholds_match_spec() -> None:
    assert SAFE_PLACES_RISK_DISTANCE_M == 1500
    assert SAFE_PLACES_CLOSE_DISTANCE_M == 300
    assert SAFE_PLACES_CLOSE_POINTS == -8
    assert PREDICTION_HORIZONS_MIN == (5, 10)
    assert STATIONARY_SPEED_MPS == 0.3
    assert BATTERY_DECAY_PERCENT_PER_5_MIN == 1
    assert BATTERY_DECAY_INTERVAL_MIN == 5

    by_name = {rule.name: rule for rule in INTERACTION_RULES}
    isolated = by_name["isolated_night"]
    assert isolated.points == 10
    assert {(item.signal, item.threshold) for item in isolated.risk_greater_than} == {
        ("time_of_day", 0.7),
        ("crowd_density", 0.7),
        ("cellular", 0.5),
    }

    distress = by_name["distress_movement"]
    assert distress.points == 10
    assert distress.movement == ("running", "fall", "sudden_stop")
    assert [(item.signal, item.threshold) for item in distress.risk_greater_than] == [
        ("crowd_density", 0.6)
    ]
