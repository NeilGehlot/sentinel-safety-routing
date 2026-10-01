"""Mock Module 1 client. Future: GET {MODULE1_URL}/api/threat/current. Module 2 works if unavailable."""
from datetime import datetime, timezone

import httpx

from app.config import settings


def current_threat(lat: float, lon: float):
    return {"score": 78, "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"latitude": lat, "longitude": lon}, "source": "mock"}


def ask_assistant(
    question: str,
    risk_score=None,
    risk_level=None,
    route_safety=None,
    nearby_safe_places=None,
) -> str:
    try:
        response = httpx.post(
            f"{settings.module1_url}/v1/assistant",
            json={
                "question": question,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "route_safety": route_safety,
                "nearby_safe_places": nearby_safe_places or [],
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["answer"]
    except Exception:
        return (
            "The safety assistant is unavailable right now. "
            "Please check your current risk level on the dashboard."
        )
