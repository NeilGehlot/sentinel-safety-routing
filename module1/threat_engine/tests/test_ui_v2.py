"""Heading-missing projection and explain=llm gating for the v2 page."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import config
from app.llm import clear_explain_cache, wire_complete
from app.main import app
from app.prediction import _future_request, project_position
from app.schemas import AssessRequest, Location

_BODY = {
    "timestamp": "2026-09-29T23:30:00+05:30",
    "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4},
    "device": {"cellular_dbm": -95, "internet_available": True, "battery_pct": 80},
    "movement": {"activity": "walking"},
    "nearby_devices": {"wifi_count": 5, "ble_count": 3},
}


def test_missing_heading_holds_position_and_advances_time() -> None:
    lat, lon = 28.4595, 77.0266
    assert project_position(lat, lon, 10.0, None, 10) == (lat, lon)
    assert project_position(lat, lon, 0.29, 90.0, 10) == (lat, lon)
    moved_lat, moved_lon = project_position(lat, lon, 0.3, 90.0, 5)
    assert moved_lon != lon
    moment = datetime(2026, 9, 29, 23, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    request = AssessRequest(timestamp=moment, location=Location(lat=lat, lon=lon, speed_mps=1.4))
    assert request.location.heading_deg is None
    future = _future_request(request, lat, lon, 10)
    assert future.location.lat == lat
    assert future.location.lon == lon
    assert future.timestamp == moment + timedelta(minutes=10)


@pytest.mark.asyncio
async def test_live_assess_does_not_call_the_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _fake(system: str, user: str) -> str:
        calls["n"] += 1
        _ = system, user
        return json.dumps(
            {"summary": "A calm check of these signals.", "recommendations": ["Stay with other people."]}
        )

    clear_explain_cache()
    wire_complete(_fake)
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "USE_LLM", True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.post("/v1/assess", json=_BODY)
        assert live.status_code == 200
        assert calls["n"] == 0
        assert live.json()["explanation"]["summary"] != "A calm check of these signals."
        monkeypatch.setattr(config, "USE_LLM", False)
        blocked = await client.post("/v1/assess?explain=llm", json=_BODY)
        assert blocked.status_code == 200
        assert calls["n"] == 0
        monkeypatch.setattr(config, "USE_LLM", True)
        phrased = await client.post("/v1/assess?explain=llm", json=_BODY)
        assert phrased.status_code == 200
        assert calls["n"] == 1
        assert phrased.json()["explanation"]["summary"] == "A calm check of these signals."
        again = await client.post("/v1/assess?explain=llm", json=_BODY)
        assert again.status_code == 200
        assert calls["n"] == 1
    wire_complete(None)
    clear_explain_cache()
