from dataclasses import replace
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models.schemas import Incident, utcnow
from app.services import route_matcher, rerouting_service as rs
from app.services import store
from app.services.geo import point_at
from app.services.routing_service import RoutingService

S, D = (26.9196, 75.7878), (26.9855, 75.8513)
c = TestClient(app)

def route(): return RoutingService().routes(S, D)[0]
def inc(lat, lon, age=5, sev=.9):
    return Incident(id="x", title="t", latitude=lat, longitude=lon, severity=sev, confidence=.9, published_at=utcnow()-timedelta(minutes=age))

def test_near_detected_far_ignored():
    r = route(); p = point_at(r["geometry"], 600)
    assert route_matcher.match(r["geometry"], [inc(*p)], 0, 8)
    assert not route_matcher.match(r["geometry"], [inc(p[0]+0.1, p[1])], 0, 8)

def test_recent_more_relevant_and_eta():
    r = route(); p = point_at(r["geometry"], 600)
    new = route_matcher.match(r["geometry"], [inc(*p, age=2)], 0, 10)[0]
    old = route_matcher.match(r["geometry"], [inc(*p, age=300)], 0, 10)[0]
    assert new["impact"] > old["impact"]
    assert abs(new["eta_min"] - 1.0) < .1

def test_no_reroute_without_incident():
    assert not rs.evaluate(RoutingService(), route(), 0, S, D, [])["recommended"]

def test_reroute_and_eta_limit(monkeypatch):
    r = route(); p = point_at(r["geometry"], 600)
    assert rs.evaluate(RoutingService(), r, 0, S, D, [inc(*p)])["recommended"]
    monkeypatch.setattr(rs, "settings", replace(rs.settings, max_extra=-100))
    assert not rs.evaluate(RoutingService(), r, 0, S, D, [inc(*p)])["recommended"]

def test_small_improvement_no_reroute(monkeypatch):
    r = route(); p = point_at(r["geometry"], 600)
    monkeypatch.setattr(rs, "settings", replace(rs.settings, min_improve=999))
    assert not rs.evaluate(RoutingService(), r, 0, S, D, [inc(*p)])["recommended"]

def test_full_demo_flow():
    body = {"start": {"latitude": S[0], "longitude": S[1]}, "destination": {"latitude": D[0], "longitude": D[1]}}
    res = c.post("/api/routes/search", json=body).json()
    assert 2 <= len(res["routes"]) <= 3
    jid = c.post("/api/navigation/start", json={"route_id": res["routes"][0]["id"]}).json()["journey_id"]
    assert c.get(f"/api/navigation/{jid}/status").json()["reroute"] is None
    assert c.post("/api/demo/inject-incident", json={"journey_id": jid}).status_code == 200
    st = c.get(f"/api/navigation/{jid}/status").json()
    assert st["reroute"]
    st = c.post(f"/api/navigation/{jid}/switch", json={"alternative_route_id": st["reroute"]["alternative"]["id"]}).json()
    assert st["status"] in ("on_track", "incident_ahead")
    assert c.get("/api/incidents/recent").status_code == 200
    assert c.post("/api/incidents/report", json={"title": "x", "latitude": 26.9, "longitude": 75.8}).status_code == 200
    assert c.get(f"/api/navigation/{jid}/route-context").status_code == 200
    assert c.post("/api/routes/recalculate", json={"journey_id": jid}).status_code == 200

def test_manual_sos_emails_guardians_and_safe_resets(monkeypatch):
    from app.api import sos

    previous_settings = store.guardian_settings
    store.guardian_settings = {
        "guardian_emails": ["one@example.com", "two@example.com"],
        "location_update_interval_minutes": 5,
        "emergency_contacts": [],
        "emergency_profile": {},
    }
    sent = []
    monkeypatch.setattr(sos, "_send_alert_email",
                        lambda emergency, email: sent.append((emergency["id"], email)) or
                        {"success": True, "recipient": email})
    try:
        started = c.post("/journeys/start", json={
            "user_name": "Test User", "latitude": S[0], "longitude": S[1]
        }).json()
        jid = started["journey_id"]
        emergency = c.post("/emergencies", json={
            "journey_id": jid, "trigger_type": "MANUAL",
            "latitude": S[0], "longitude": S[1],
        })
        assert emergency.status_code == 200
        assert emergency.json()["email_status"] == "sent"
        assert [email for _, email in sent] == ["one@example.com", "two@example.com"]
        safe = c.post("/signals", json={"journey_id": jid, "signal_type": "SAFE"})
        assert safe.json()["status"] == "IDLE"
        assert jid not in store.sos_journeys
        assert store.emergencies[emergency.json()["emergency_id"]]["status"] == "RESOLVED"
    finally:
        store.guardian_settings = previous_settings
