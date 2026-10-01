"""Configurable route scoring. Module 1's threat score can be added as another factor/weight."""
import hashlib
from app.config import settings
from app.services import osm_route_factors

WEIGHTS = {"historical_crime": .25, "lighting": .15, "crowd": .10,
           "traffic": .15, "connectivity": .15, "safe_locations": .20}

_OSM_FACTORS = ("lighting", "connectivity", "safe_locations")


def _hash_factors(geom) -> dict:
    h = hashlib.md5(str([[round(a, 3), round(b, 3)] for a, b in geom[::10]]).encode()).digest()
    return {k: 72 + h[n] % 21 for n, k in enumerate(WEIGHTS)}


def base_factors(geom) -> dict:
    """Prototype static factors (0-100). OSM fills lighting, connectivity, and safe_locations."""
    factors = _hash_factors(geom)
    osm = osm_route_factors.try_osm_factors(geom)
    if osm:
        for key in _OSM_FACTORS:
            if key in osm:
                factors[key] = osm[key]
    return factors


def score(geom, effects) -> dict:
    f = base_factors(geom)
    base = sum(f[k]*w for k, w in WEIGHTS.items())
    penalty = min(sum(e["impact"] for e in effects)*settings.penalty_max, 60)
    return {"safety": round(max(base - penalty, 0), 1), "base_safety": round(base, 1),
            "factors": f, "incident_count": len(effects)}


# Recommended-route ranking among real ORS (or mock) candidates:
#   osm_quality = (lighting + connectivity + safe_locations) / 3     # 0–100
#   shortest    = 100 * min(duration_s) / duration_s                 # 100 = fastest
#   rank_score  = 0.6 * osm_quality + 0.4 * shortest
# crowd, traffic, and historical_crime are not used for selection.
OSM_RANK_WEIGHT = 0.6
SHORTEST_RANK_WEIGHT = 0.4


def osm_quality(factors) -> float:
    return (
        float(factors.get("lighting", 0))
        + float(factors.get("connectivity", 0))
        + float(factors.get("safe_locations", 0))
    ) / 3.0


def shortest_index(duration_s, min_duration_s) -> float:
    if duration_s <= 0 or min_duration_s <= 0:
        return 0.0
    return 100.0 * min_duration_s / duration_s


def rank_score(factors, duration_s, min_duration_s) -> float:
    return OSM_RANK_WEIGHT * osm_quality(factors) + SHORTEST_RANK_WEIGHT * shortest_index(
        duration_s, min_duration_s
    )


def mark_recommended(routes) -> list:
    """Set rank_score and recommended on ORS/mock candidates. Mutates and returns routes."""
    if not routes:
        return routes
    min_dur = min((float(r.get("duration_s") or 0) for r in routes), default=0.0)
    if min_dur <= 0:
        min_dur = min((float(r.get("distance_m") or 1) for r in routes), default=1.0)
    for r in routes:
        duration = float(r.get("duration_s") or 0) or float(r.get("distance_m") or 1)
        r["rank_score"] = round(rank_score(r.get("factors") or {}, duration, min_dur), 2)
    best = max(routes, key=lambda r: (r["rank_score"], -float(r.get("duration_s") or 0)))
    for r in routes:
        r["recommended"] = r is best
    return routes
