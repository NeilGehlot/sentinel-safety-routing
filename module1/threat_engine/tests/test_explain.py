"""Rule-based explanation stays calm and uses live context."""

import pytest

from app.engine import assess
from app.schemas import AssessRequest

SAMPLE = {
    "session_id": "abc",
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
    "device": {"battery_pct": 18, "cellular_dbm": -108, "internet_available": False},
    "nearby_devices": {"ble_count": 3, "wifi_count": 2},
    "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
}


@pytest.mark.asyncio
async def test_summary_and_recommendations_use_live_context() -> None:
    response = await assess(AssessRequest.model_validate(SAMPLE))
    text = response.explanation.summary + " ".join(response.recommendations)
    lowered = text.lower()
    assert "follow" not in lowered
    assert "attack" not in lowered
    assert len(response.recommendations) <= 3
    assert any("18%" in item for item in response.recommendations)
    assert any("800 m" in item for item in response.recommendations)
    assert response.explanation.summary
    assert response.explanation.contributors
