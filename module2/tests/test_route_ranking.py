"""Recommended route = OSM quality + historical crime + shortest path."""
from app.services import route_scorer


def _route(rid, duration_s, lighting, connectivity, safe_locations, extra=None):
    factors = {
        "lighting": lighting,
        "connectivity": connectivity,
        "safe_locations": safe_locations,
        "historical_crime": 70,
        "crowd": 99,
        "traffic": 99,
    }
    if extra:
        factors.update(extra)
    return {
        "id": rid,
        "duration_s": duration_s,
        "distance_m": duration_s * 10,
        "factors": factors,
        "safety": 50,
    }


def _recommended(routes):
    route_scorer.mark_recommended(routes)
    winners = [r["id"] for r in routes if r["recommended"]]
    assert len(winners) == 1
    return winners[0]


def test_shorter_and_safer_beats_longer_and_worse():
    better = _route("short_safe", 600, 90, 88, 92, extra={"historical_crime": 90})
    worse = _route("long_unsafe", 1200, 45, 42, 40, extra={"historical_crime": 40})
    assert _recommended([worse, better]) == "short_safe"
    assert better["rank_score"] > worse["rank_score"]


def test_equal_osm_and_crime_prefers_shortest_duration():
    fast = _route("fast", 400, 70, 70, 70)
    slow = _route("slow", 900, 70, 70, 70)
    assert _recommended([slow, fast]) == "fast"


def test_equal_duration_prefers_better_osm_factors():
    lit = _route("lit", 800, 92, 90, 88)
    dark = _route("dark", 800, 50, 48, 45)
    assert _recommended([dark, lit]) == "lit"


def test_crowd_traffic_do_not_change_selection():
    a = _route("a", 700, 80, 80, 80, extra={"crowd": 10, "traffic": 10, "historical_crime": 70})
    b = _route("b", 700, 80, 80, 80, extra={"crowd": 99, "traffic": 99, "historical_crime": 70})
    route_scorer.mark_recommended([a, b])
    assert a["rank_score"] == b["rank_score"]


def test_lower_historical_crime_safety_loses_when_osm_and_duration_match():
    safer = _route("safer_crime", 700, 80, 80, 80, extra={"historical_crime": 90})
    riskier = _route("riskier_crime", 700, 80, 80, 80, extra={"historical_crime": 20})
    assert _recommended([riskier, safer]) == "safer_crime"
    assert safer["rank_score"] > riskier["rank_score"]


def test_safer_osm_can_beat_slightly_longer_route():
    longer_safer = _route("safer", 720, 95, 94, 96)
    shorter_worse = _route("faster", 600, 50, 50, 50)
    assert _recommended([shorter_worse, longer_safer]) == "safer"


def test_rank_formula_is_osm_crime_and_shortest():
    factors = {
        "lighting": 90,
        "connectivity": 60,
        "safe_locations": 30,
        "historical_crime": 80,
    }
    # osm_quality = 60; crime = 80; shortest vs 100s duration = 50
    # rank = 0.45*60 + 0.25*80 + 0.30*50 = 27 + 20 + 15 = 62
    assert route_scorer.rank_score(factors, 200, 100) == 62.0
