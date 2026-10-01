from app.services.crime_lookup import NATIONAL_MEAN_SAFETY, historical_crime_for, is_special_unit
from app.services.route_scorer import WEIGHTS, live_factors, score, score_point


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
    assert WEIGHTS["historical_crime"] == 0.20
    live = WEIGHTS["lighting"] + WEIGHTS["crowd"] + WEIGHTS["traffic"]
    assert abs(live - 0.80) < 1e-9
    assert abs(WEIGHTS["lighting"] - WEIGHTS["crowd"]) < 1e-12
    assert abs(WEIGHTS["crowd"] - WEIGHTS["traffic"]) < 1e-12


def test_unknown_point_uses_national_mean():
    hit = historical_crime_for(0.0, 0.0)
    assert hit["matched"] is False
    assert hit["safety_score"] == NATIONAL_MEAN_SAFETY
    assert hit["safety_score"] not in (0, 100, 0.0, 100.0)


def test_crime_never_zero_or_hundred_for_known_cities():
    for lat, lng in ((19.076, 72.8777), (26.9124, 75.7873), (28.6139, 77.209)):
        hit = historical_crime_for(lat, lng)
        assert 0 < hit["safety_score"] < 100
        assert hit["safety_score"] not in (0, 100)


def test_special_units_filtered():
    assert is_special_unit("Mumbai Railway")
    assert is_special_unit("CID")
    assert is_special_unit("ATS")
    assert not is_special_unit("Jaipur")


def test_live_factors_move_without_crime_change():
    a = score_point(26.9124, 75.7873, hour=14)
    b = score_point(26.9200, 75.8000, hour=14)
    assert a["crime"]["place_key"] == b["crime"]["place_key"]
    assert a["factors"]["historical_crime"] == b["factors"]["historical_crime"]
    live_changed = any(a["factors"][k] != b["factors"][k] for k in ("lighting", "crowd", "traffic"))
    assert live_changed


def test_route_score_keeps_incident_penalty():
    geom = [[26.91, 75.78], [26.92, 75.79], [26.93, 75.80]]
    clean = score(geom, [])
    hit = score(geom, [{"impact": 0.5}])
    assert hit["safety"] < clean["safety"]
    assert set(clean["factors"]) >= {"historical_crime", "lighting", "crowd", "traffic"}


def test_point_safety_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app
    res = TestClient(app).get("/api/routes/point-safety", params={"latitude": 26.9124, "longitude": 75.7873})
    assert res.status_code == 200
    body = res.json()
    assert "historical_crime" in body["factors"]
    assert 0 < body["crime"]["safety_score"] < 100
