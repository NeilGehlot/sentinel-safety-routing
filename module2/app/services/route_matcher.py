"""Incident->route matching: spatial (Shapely), temporal decay, ETA, explainable impact."""
import math
from shapely.geometry import Point
from app.config import settings
from app.models.schemas import aware, utcnow
from app.services.geo import to_line, to_xy

def temporal_weight(age_min: float) -> float:
    return math.exp(-max(age_min, 0)/settings.decay)

def match(geom, incidents, progress_m, speed_mps, now=None):
    """impact = severity x spatial x temporal x confidence, for incidents near the remaining route."""
    now = now or utcnow()
    ln, lat0 = to_line(geom)
    out = []
    for i in incidents:
        p = Point(*to_xy(i.latitude, i.longitude, lat0))
        d = ln.distance(p)
        if d > settings.radius:
            continue
        along = ln.project(p)
        if along < progress_m - 50:
            continue
        ahead = max(along - progress_m, 0.0)
        age = (now - aware(i.published_at)).total_seconds()/60
        out.append({"incident": i, "distance_to_route_m": d, "distance_ahead_m": ahead,
                    "eta_min": ahead/max(speed_mps, 0.1)/60, "age_min": age,
                    "impact": i.severity*(1 - d/settings.radius)*temporal_weight(age)*i.confidence})
    return sorted(out, key=lambda x: x["distance_ahead_m"])
