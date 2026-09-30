"""Scoring invariant, renormalized weights, and the section 8 adjustments."""

from app.providers.base import SignalResult
from app.scoring import safe_place_adjustment, score_signals


def _signal(name: str, risk: float, available: bool = True, **details: float | str | bool | None) -> SignalResult:
    return SignalResult(name=name, risk=risk, reason=name, available=available, details=dict(details))


def test_contributor_points_sum_to_the_pre_clamp_score() -> None:
    signals = [
        _signal("crime_risk", 1.0),
        _signal("time_of_day", 1.0),
        _signal("crowd_density", 1.0),
        _signal("cellular", 1.0),
        _signal("movement", 1.0, activity="running"),
        _signal("safe_places", 0.0, distance_m=0.0),
    ]
    breakdown = score_signals(signals)
    assert sum(item.points for item in breakdown.contributors) == breakdown.pre_clamp_score
    assert breakdown.score == max(0, min(100, breakdown.pre_clamp_score))


def test_missing_signals_renormalize_and_are_not_zero_risk() -> None:
    crime = _signal("crime_risk", 1.0)
    only = score_signals([crime])
    missing_weather = score_signals([crime, _signal("weather", 0.0, available=False)])
    zero_weather = score_signals([crime, _signal("weather", 0.0, available=True)])
    assert only.pre_clamp_score == 100
    assert missing_weather.pre_clamp_score == 100
    assert all(item.signal != "weather" for item in missing_weather.contributors)
    assert zero_weather.pre_clamp_score == 75
    assert zero_weather.pre_clamp_score < only.pre_clamp_score


def test_gps_weight_does_not_change_the_score() -> None:
    crime = _signal("crime_risk", 1.0)
    with_gps = score_signals([crime, _signal("gps", 1.0)])
    assert score_signals([crime]).pre_clamp_score == with_gps.pre_clamp_score
    assert all(item.signal != "gps" for item in with_gps.contributors)


def test_safe_place_negative_within_300_meters() -> None:
    assert safe_place_adjustment(0) == -8
    assert safe_place_adjustment(150) == -4
    assert safe_place_adjustment(300) == 0
    assert safe_place_adjustment(800) == 0
    close = score_signals([_signal("safe_places", 0.0, distance_m=0.0)])
    assert close.pre_clamp_score == -8
    assert close.score == 0
    assert sum(item.points for item in close.contributors) == -8


def test_isolated_night_and_distress_movement_boosts() -> None:
    isolated = score_signals(
        [
            _signal("time_of_day", 0.71),
            _signal("crowd_density", 0.71),
            _signal("cellular", 0.51),
        ]
    )
    assert any(item.signal == "isolated_night" and item.points == 10 for item in isolated.contributors)
    just_under = score_signals(
        [
            _signal("time_of_day", 0.7),
            _signal("crowd_density", 0.71),
            _signal("cellular", 0.51),
        ]
    )
    assert all(item.signal != "isolated_night" for item in just_under.contributors)

    distress = score_signals(
        [
            _signal("crowd_density", 0.61),
            _signal("movement", 0.85, activity="running"),
        ]
    )
    assert any(item.signal == "distress_movement" and item.points == 10 for item in distress.contributors)
    walking = score_signals(
        [
            _signal("crowd_density", 0.9),
            _signal("movement", 0.15, activity="walking"),
        ]
    )
    assert all(item.signal != "distress_movement" for item in walking.contributors)
    missing_crowd = score_signals([_signal("movement", 0.85, activity="fall")])
    assert all(item.signal != "distress_movement" for item in missing_crowd.contributors)
