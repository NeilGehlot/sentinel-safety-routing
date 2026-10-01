"""Route scoring: 22.5% historical crime lookup; five original live/hash factors share 77.5%.

Lighting, connectivity, and safe_locations prefer OSM Overpass when available.
Recommended-route ranking uses OSM quality, historical-crime lookup, and shortest duration.
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.services import osm_route_factors
from app.services.crime_lookup import historical_crime_for
from app.services.geo import haversine, path_length, point_at

# Original SOS_feature relative shares for the five non-crime keys, scaled to 0.775.
_ORIG_LIVE = {
    "lighting": 0.15,
    "crowd": 0.10,
    "traffic": 0.15,
    "connectivity": 0.15,
    "safe_locations": 0.20,
}
_LIVE_SCALE = 0.775 / sum(_ORIG_LIVE.values())
WEIGHTS = {
    "historical_crime": 0.225,
    **{k: v * _LIVE_SCALE for k, v in _ORIG_LIVE.items()},
}
FACTOR_KEYS = tuple(WEIGHTS)
SAMPLE_EVERY_M = 1500.0
_OSM_FACTORS = ("lighting", "connectivity", "safe_locations")

# Recommended-route ranking among real ORS (or mock) candidates:
#   osm_quality = (lighting + connectivity + safe_locations) / 3     # 0–100
#   crime       = historical_crime factor (NCRB lookup safety_score) # 0–100
#   shortest    = 100 * min(duration_s) / duration_s                 # 100 = fastest
#   rank_score  = 0.45 * osm_quality + 0.25 * crime + 0.30 * shortest
# crowd and traffic are not used for selection. Pin safety still uses WEIGHTS.
OSM_RANK_WEIGHT = 0.45
CRIME_RANK_WEIGHT = 0.25
SHORTEST_RANK_WEIGHT = 0.30


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def live_factors(lat: float, lng: float, hour: Optional[int] = None) -> dict:
    """OSM-style proxies that change with position and hour, independent of crime lookup."""
    if hour is None:
        hour = datetime.now(timezone.utc).astimezone().hour
    h = hashlib.md5(f"{round(lat, 4)}|{round(lng, 4)}".encode()).digest()
    night = 1.0 if hour >= 21 or hour < 5 else (0.45 if hour >= 18 or hour < 7 else 0.0)
    rush = 1.0 if hour in (8, 9, 10, 17, 18, 19) else 0.0
    lighting = 78 + (h[0] % 17) - night * (12 + h[1] % 8)
    crowd = 70 + (h[2] % 19) - night * (8 + h[3] % 6) + (5 if 11 <= hour <= 16 else 0)
    traffic = 74 + (h[4] % 16) - rush * (10 + h[5] % 8)
    seed = hashlib.md5(f"{round(lat, 3)}|{round(lng, 3)}".encode()).digest()
    hashed = {k: 72 + seed[n] % 21 for n, k in enumerate(FACTOR_KEYS)}
    return {
        "lighting": round(_clamp(lighting), 1),
        "crowd": round(_clamp(crowd), 1),
        "traffic": round(_clamp(traffic), 1),
        "connectivity": hashed["connectivity"],
        "safe_locations": hashed["safe_locations"],
    }


def _sample_distances(geom) -> list[float]:
    total = path_length(geom) if geom and len(geom) >= 2 else 0.0
    if total <= 0:
        return [0.0]
    n = max(3, int(total / SAMPLE_EVERY_M) + 1)
    return [total * i / (n - 1) for i in range(n)]


def _sample_weights(distances: list[float]) -> list[float]:
    if len(distances) == 1:
        return [1.0]
    weights = []
    for i, d in enumerate(distances):
        prev = distances[i - 1] if i else d
        nxt = distances[i + 1] if i + 1 < len(distances) else d
        w = max((d - prev) / 2 + (nxt - d) / 2, 1.0)
        weights.append(w)
    s = sum(weights)
    return [w / s for w in weights]


def factors_for_point(lat: float, lng: float, hour: Optional[int] = None) -> dict:
    live = live_factors(lat, lng, hour)
    crime = historical_crime_for(lat, lng)
    return {**live, "historical_crime": crime["safety_score"], "_crime": crime}


def _weighted_mean(samples: list[dict], keys: list[str], weights: list[float]) -> dict:
    out = {}
    for k in keys:
        out[k] = round(sum(s[k] * w for s, w in zip(samples, weights)), 1)
    return out


def _overlay_osm(geom, factors: dict) -> dict:
    osm = osm_route_factors.try_osm_factors(geom)
    if not osm:
        return factors
    for key in _OSM_FACTORS:
        if key in osm:
            factors[key] = osm[key]
    return factors


def base_factors(geom, hour: Optional[int] = None) -> dict:
    if not geom:
        f = factors_for_point(0.0, 0.0, hour)
        f.pop("_crime", None)
        return f
    distances = _sample_distances(geom)
    weights = _sample_weights(distances)
    samples = []
    for d in distances:
        lat, lng = point_at(geom, d) if len(geom) >= 2 else geom[0]
        samples.append(factors_for_point(lat, lng, hour))
    out = _weighted_mean(samples, list(FACTOR_KEYS), weights)
    if len(geom) >= 2:
        seed = hashlib.md5(str([[round(a, 3), round(b, 3)] for a, b in geom[::10]]).encode()).digest()
        hashed = {k: 72 + seed[n] % 21 for n, k in enumerate(FACTOR_KEYS)}
        out["connectivity"] = hashed["connectivity"]
        out["safe_locations"] = hashed["safe_locations"]
    return _overlay_osm(geom, out)


def _incident_penalty(effects) -> float:
    if not effects:
        return 0.0
    return min(sum(e["impact"] for e in effects) * settings.penalty_max, 60)


def score(geom, effects, hour: Optional[int] = None) -> dict:
    f = base_factors(geom, hour)
    base = sum(f[k] * w for k, w in WEIGHTS.items())
    penalty = _incident_penalty(effects)
    return {
        "safety": round(max(base - penalty, 0), 1),
        "base_safety": round(base, 1),
        "factors": f,
        "incident_count": len(effects or []),
    }


def score_point(lat: float, lng: float, incidents=None, hour: Optional[int] = None) -> dict:
    packed = factors_for_point(lat, lng, hour)
    crime = packed.pop("_crime")
    f = {k: packed[k] for k in WEIGHTS}
    base = sum(f[k] * w for k, w in WEIGHTS.items())
    effects = []
    for i in incidents or []:
        d = haversine((lat, lng), (i.latitude, i.longitude))
        if d > settings.radius:
            continue
        impact = getattr(i, "severity", 0.5) * (1 - d / settings.radius) * getattr(i, "confidence", 0.8)
        effects.append({"impact": impact, "incident": i})
    penalty = _incident_penalty(effects)
    return {
        "safety": round(max(base - penalty, 0), 1),
        "base_safety": round(base, 1),
        "factors": f,
        "incident_count": len(effects),
        "crime": {
            "safety_score": crime["safety_score"],
            "source": crime["source"],
            "district": crime.get("district"),
            "city": crime.get("city"),
            "state_ut": crime.get("state_ut"),
            "place_key": crime.get("place_key"),
            "matched": crime.get("matched"),
        },
        "latitude": lat,
        "longitude": lng,
    }


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


def crime_quality(factors) -> float:
    return float(factors.get("historical_crime", 0))


def rank_score(factors, duration_s, min_duration_s) -> float:
    return (
        OSM_RANK_WEIGHT * osm_quality(factors)
        + CRIME_RANK_WEIGHT * crime_quality(factors)
        + SHORTEST_RANK_WEIGHT * shortest_index(duration_s, min_duration_s)
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
