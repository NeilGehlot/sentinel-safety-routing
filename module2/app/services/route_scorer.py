"""Route and point scoring: 20% historical crime, 80% live lighting/crowd/traffic."""
import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.services.crime_lookup import historical_crime_for
from app.services.geo import haversine, path_length, point_at

LIVE_SHARE = 0.80
LIVE_EACH = LIVE_SHARE / 3
WEIGHTS = {
    "historical_crime": 0.20,
    "lighting": LIVE_EACH,
    "crowd": LIVE_EACH,
    "traffic": LIVE_EACH,
}
SAMPLE_EVERY_M = 1500.0


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
    return {
        "lighting": round(_clamp(lighting), 1),
        "crowd": round(_clamp(crowd), 1),
        "traffic": round(_clamp(traffic), 1),
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
    keys = ["historical_crime", "lighting", "crowd", "traffic"]
    return _weighted_mean(samples, keys, weights)


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
