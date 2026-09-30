"""App boot, GET /v1/health, and the phase 1 assess route."""

import httpx
import pytest

from app.main import app, create_app

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


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_app_boots_a_fresh_instance() -> None:
    fresh = create_app()
    transport = httpx.ASGITransport(app=fresh)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_only_assess_and_health_are_mounted() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/v1/health" in paths
    assert "/v1/assess" in paths
    assert "/v1/assess/point" not in paths
    assert not any(path.startswith("/v1/scenarios") for path in paths)


@pytest.mark.asyncio
async def test_assess_accepts_the_sample_and_keeps_removed_routes_gone() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/assess", json=SAMPLE_ASSESS_REQUEST)
        removed = await client.post(
            "/v1/assess/point",
            json={"lat": 28.4595, "lon": 77.0266, "timestamp": "2026-09-29T23:40:00+05:30"},
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "session_id",
        "current_score",
        "predicted",
        "explanation",
        "recommendations",
    }
    assert body["session_id"] == "abc"
    assert [item["horizon_min"] for item in body["predicted"]] == [5, 10]
    assert 0 <= body["current_score"] <= 100
    assert body["explanation"]["summary"]
    assert body["explanation"]["contributors"]
    assert removed.status_code == 404


@pytest.mark.asyncio
async def test_static_index_is_served_at_root() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/")
        script = await client.get("/app.js")
        health = await client.get("/v1/health")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Your situation" in page.text
    assert "Your safety check" in page.text
    assert script.status_code == 200
    assert "sudden_stop" in script.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
