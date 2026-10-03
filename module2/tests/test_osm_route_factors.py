"""OSM lighting / connectivity / safe_locations factors (Overpass mocked)."""
import httpx
import pytest

from app.services import osm_route_factors, route_scorer

GEOM = [[26.91, 75.78], [26.92, 75.79], [26.93, 75.80], [26.94, 75.81]]


def _el(kind, eid, lat, lon, tags, el_type="node"):
    item = {"type": el_type, "id": eid, "tags": tags}
    if el_type == "way":
        item["center"] = {"lat": lat, "lon": lon}
    else:
        item["lat"] = lat
        item["lon"] = lon
    return item


RICH = [
    _el("lamp", 1, 26.92, 75.79, {"highway": "street_lamp"}),
    _el("lamp", 2, 26.921, 75.791, {"highway": "street_lamp"}),
    _el("lit", 3, 26.922, 75.792, {"highway": "residential", "lit": "yes"}, "way"),
    _el("j", 4, 26.923, 75.793, {"highway": "crossing"}),
    _el("j", 5, 26.924, 75.794, {"junction": "yes"}),
    _el("rd", 6, 26.925, 75.795, {"highway": "primary"}, "way"),
    _el("rd", 7, 26.926, 75.796, {"highway": "residential"}, "way"),
    _el("pd", 8, 26.92, 75.79, {"amenity": "police", "name": "City Police"}),
    _el("hs", 9, 26.93, 75.80, {"amenity": "hospital"}),
]


def test_sample_points_cap_and_include_ends():
    long_geom = [[26.9 + i * 0.01, 75.8] for i in range(40)]
    pts = osm_route_factors.sample_points(long_geom, max_points=5, min_spacing_m=50)
    assert pts[0] == long_geom[0]
    assert len(pts) <= 5


def test_factors_from_elements_higher_with_osm_features():
    rich = osm_route_factors.factors_from_elements(RICH, GEOM)
    empty = osm_route_factors.factors_from_elements([], GEOM)
    assert rich["lighting"] > empty["lighting"]
    assert rich["connectivity"] > empty["connectivity"]
    assert rich["safe_locations"] > empty["safe_locations"]
    for key, value in rich.items():
        assert 40 <= value <= 96, key


def test_places_from_elements_keeps_named_refuges():
    places = osm_route_factors.places_from_elements(RICH, GEOM)
    assert places[0]["name"] == "City Police"
    assert places[0]["kind"] == "police"
    assert places[1]["name"] == "Hospital"
    assert places[1]["kind"] == "hospital"
    assert all("latitude" in place and "longitude" in place for place in places)


def test_safe_places_for_uses_same_payload(monkeypatch):
    monkeypatch.setattr(osm_route_factors, "fetch_overpass_payload", lambda query: {"elements": RICH})
    osm_route_factors.clear_cache()
    places = osm_route_factors.safe_places_for(GEOM)
    assert [place["kind"] for place in places] == ["police", "hospital"]


def test_lit_no_lowers_lighting():
    yes = osm_route_factors.factors_from_elements(
        [_el("w", 1, 26.92, 75.79, {"highway": "residential", "lit": "yes"}, "way")], GEOM
    )
    no = osm_route_factors.factors_from_elements(
        [_el("w", 1, 26.92, 75.79, {"highway": "residential", "lit": "no"}, "way")], GEOM
    )
    assert yes["lighting"] > no["lighting"]


def test_try_osm_factors_uses_payload(monkeypatch):
    def _ok(query: str):
        assert "street_lamp" in query
        assert "amenity" in query
        return {"elements": RICH}

    monkeypatch.setattr(osm_route_factors, "fetch_overpass_payload", _ok)
    osm_route_factors.clear_cache()
    got = osm_route_factors.try_osm_factors(GEOM)
    assert got is not None
    assert set(got) == {"lighting", "connectivity", "safe_locations"}


def test_try_osm_factors_none_on_timeout(monkeypatch):
    def _timeout(query: str):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(osm_route_factors, "fetch_overpass_payload", _timeout)
    assert osm_route_factors.try_osm_factors(GEOM) is None


def test_base_factors_prefer_osm_over_hash(monkeypatch):
    osm = {"lighting": 90, "connectivity": 88, "safe_locations": 91}

    monkeypatch.setattr(osm_route_factors, "try_osm_factors", lambda geom: osm)
    factors = route_scorer.base_factors(GEOM)
    assert factors["lighting"] == 90
    assert factors["connectivity"] == 88
    assert factors["safe_locations"] == 91
    assert 0 < factors["historical_crime"] < 100
    assert 0 <= factors["crowd"] <= 100
    assert 0 <= factors["traffic"] <= 100


def test_base_factors_hash_fallback_when_overpass_fails():
    factors = route_scorer.base_factors(GEOM)
    assert set(factors) >= set(route_scorer.WEIGHTS)
    assert 0 < factors["historical_crime"] < 100
    assert 72 <= factors["connectivity"] <= 92
    assert 72 <= factors["safe_locations"] <= 92
    for key in ("lighting", "crowd", "traffic"):
        assert 0 <= factors[key] <= 100


def test_score_still_applies_incident_penalty(monkeypatch):
    monkeypatch.setattr(
        osm_route_factors,
        "try_osm_factors",
        lambda geom: {"lighting": 80, "connectivity": 80, "safe_locations": 80},
    )
    none = route_scorer.score(GEOM, [])
    hit = route_scorer.score(GEOM, [{"impact": 0.5}])
    assert hit["safety"] < none["safety"]
    assert none["incident_count"] == 0
    assert hit["incident_count"] == 1
