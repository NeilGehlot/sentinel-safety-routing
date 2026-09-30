"""Phase 1 schema checks for the section 5 assess contract."""

import pytest
from pydantic import ValidationError

from app.schemas import AssessRequest, AssessResponse

SAMPLE_ASSESS_REQUEST: dict[str, object] = {
    "session_id": "abc",
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {
        "lat": 28.4595,
        "lon": 77.0266,
        "speed_mps": 1.4,
        "heading_deg": 90,
    },
    "device": {
        "battery_pct": 18,
        "cellular_dbm": -108,
        "internet_available": False,
    },
    "nearby_devices": {"ble_count": 3, "wifi_count": 2},
    "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
}

MINIMAL_ASSESS_REQUEST: dict[str, object] = {
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {"lat": 28.4595, "lon": 77.0266},
}

SAMPLE_ASSESS_RESPONSE: dict[str, object] = {
    "session_id": "abc",
    "current_score": 86,
    "predicted": [
        {"horizon_min": 5, "score": 91},
        {"horizon_min": 10, "score": 88},
    ],
    "explanation": {
        "summary": (
            "Your score is high mainly because you are in an area with elevated "
            "recorded incidents, it is late at night, and signal is very weak."
        ),
        "contributors": [
            {
                "signal": "crime_risk",
                "points": 20,
                "reason": "Late hour and dense nightlife area raise modeled risk",
            },
            {
                "signal": "cellular",
                "points": 16,
                "reason": "Very weak cellular signal",
            },
            {"signal": "time_of_day", "points": 12, "reason": "Late night"},
            {
                "signal": "safe_places",
                "points": -3,
                "reason": "Metro station 400 m away",
            },
        ],
    },
    "recommendations": [
        "Metro station is 400 m east. Heading there puts you near people and better signal.",
        "Your battery is at 18%. Consider enabling battery saver.",
    ],
}


def test_sample_request_validates() -> None:
    model = AssessRequest.model_validate(SAMPLE_ASSESS_REQUEST)
    assert model.session_id == "abc"
    assert model.location.lat == 28.4595
    assert model.location.lon == 77.0266
    assert model.location.speed_mps == 1.4
    assert model.movement is not None
    assert model.movement.accel_window == [[0.1, 9.8, 0.3]]
    assert model.movement.sampling_hz == 50
    assert model.movement.activity is None


def test_minimal_location_and_timestamp_request_validates() -> None:
    model = AssessRequest.model_validate(MINIMAL_ASSESS_REQUEST)
    assert model.session_id is None
    assert model.device is None
    assert model.nearby_devices is None
    assert model.movement is None
    assert model.location.speed_mps is None
    assert model.location.heading_deg is None


def test_activity_only_movement_validates() -> None:
    payload = {
        **MINIMAL_ASSESS_REQUEST,
        "movement": {"activity": "walking"},
    }
    model = AssessRequest.model_validate(payload)
    assert model.movement is not None
    assert model.movement.activity == "walking"
    assert model.movement.accel_window is None


@pytest.mark.parametrize(
    "activity",
    ["stationary", "walking", "running", "vehicle", "fall", "sudden_stop"],
)
def test_allowed_activities(activity: str) -> None:
    payload = {
        **MINIMAL_ASSESS_REQUEST,
        "movement": {"activity": activity},
    }
    model = AssessRequest.model_validate(payload)
    assert model.movement is not None
    assert model.movement.activity == activity


def test_sudden_stop_activity_validates() -> None:
    payload = {
        **MINIMAL_ASSESS_REQUEST,
        "movement": {"activity": "sudden_stop"},
    }
    model = AssessRequest.model_validate(payload)
    assert model.movement is not None
    assert model.movement.activity == "sudden_stop"


def test_removed_request_fields_are_rejected() -> None:
    payload = {
        **MINIMAL_ASSESS_REQUEST,
        "motion": {"activity": "walking"},
    }
    with pytest.raises(ValidationError):
        AssessRequest.model_validate(payload)


def test_location_and_timestamp_are_required() -> None:
    with pytest.raises(ValidationError):
        AssessRequest.model_validate({"timestamp": "2026-09-29T23:40:00+05:30"})
    with pytest.raises(ValidationError):
        AssessRequest.model_validate({"location": {"lat": 28.4595, "lon": 77.0266}})


def test_sample_response_validates() -> None:
    model = AssessResponse.model_validate(SAMPLE_ASSESS_RESPONSE)
    assert model.current_score == 86
    assert [item.horizon_min for item in model.predicted] == [5, 10]
    assert model.explanation.contributors[3].points == -3
    assert len(model.recommendations) == 2
