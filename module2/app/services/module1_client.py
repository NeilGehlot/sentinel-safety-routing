"""Mock Module 1 client. Future: GET {MODULE1_URL}/api/threat/current. Module 2 works if unavailable."""
from datetime import datetime, timezone
def current_threat(lat: float, lon: float):
    return {"score": 78, "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"latitude": lat, "longitude": lon}, "source": "mock"}
