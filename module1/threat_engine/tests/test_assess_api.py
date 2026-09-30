"""POST /v1/assess returns a section 5 score and both predicted horizons."""

from datetime import timedelta

import httpx
import pytest

from app.engine import assess
from app.main import app
from app.schemas import AssessRequest, Location

SAMPLE = {
    "session_id": "abc",
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
    "device": {"battery_pct": 18, "cellular_dbm": -108, "internet_available": False},
    "nearby_devices": {"ble_count": 3, "wifi_count": 2},
    "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
}

MINIMAL = {
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {"lat": 28.4595, "lon": 77.0266},
}


def _assert_scored_body(body: dict[str, object]) -> None:
    assert set(body) == {
        "session_id",
        "current_score",
        "predicted",
        "explanation",
        "recommendations",
    }
    predicted = body["predicted"]
    assert isinstance(predicted, list)
    assert [item["horizon_min"] for item in predicted] == [5, 10]
    for item in predicted:
        assert set(item) == {"horizon_min", "score"}
        assert 0 <= int(item["score"]) <= 100
    explanation = body["explanation"]
    assert isinstance(explanation, dict)
    contributors = explanation["contributors"]
    assert isinstance(contributors, list)
    assert contributors
    total = sum(int(item["points"]) for item in contributors)
    score = int(body["current_score"])
    assert 0 <= score <= 100
    assert score == max(0, min(100, total))
    assert "gps" not in {item["signal"] for item in contributors}
    recommendations = body["recommendations"]
    assert isinstance(recommendations, list)
    assert len(recommendations) <= 3


@pytest.mark.asyncio
async def test_sample_request_returns_a_valid_score() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/assess", json=SAMPLE)
    assert response.status_code == 200
    body = response.json()
    _assert_scored_body(body)
    assert body["session_id"] == "abc"
    assert body["current_score"] > 0


@pytest.mark.asyncio
async def test_minimal_location_and_timestamp_returns_a_valid_score() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/assess", json=MINIMAL)
    assert response.status_code == 200
    body = response.json()
    _assert_scored_body(body)
    names = {item["signal"] for item in body["explanation"]["contributors"]}
    assert "cellular" not in names
    assert "connectivity_battery" not in names
    assert "connectivity_internet" not in names
    assert "nearby_devices" not in names
    assert "movement" not in names
    crime = next(item for item in body["explanation"]["contributors"] if item["signal"] == "crime_risk")
    assert crime["points"] > round(18 * 0.82)


@pytest.mark.asyncio
async def test_sudden_stop_uses_session_memory_inside_the_engine() -> None:
    first = AssessRequest.model_validate(SAMPLE)
    moving = first.model_copy(
        update={
            "session_id": "stop-1",
            "location": Location(lat=28.4595, lon=77.0266, speed_mps=3.0, heading_deg=90),
        }
    )
    stopped = moving.model_copy(
        update={
            "timestamp": moving.timestamp + timedelta(seconds=20),
            "location": Location(lat=28.4595, lon=77.0266, speed_mps=0.0, heading_deg=90),
        }
    )
    await assess(moving)
    response = await assess(stopped)
    movement = next(item for item in response.explanation.contributors if item.signal == "movement")
    assert "suddenly" in movement.reason
    other = stopped.model_copy(update={"session_id": "stop-2"})
    fresh = await assess(other)
    fresh_movement = next(item for item in fresh.explanation.contributors if item.signal == "movement")
    assert "suddenly" not in fresh_movement.reason
