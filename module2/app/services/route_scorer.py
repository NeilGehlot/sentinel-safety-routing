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
