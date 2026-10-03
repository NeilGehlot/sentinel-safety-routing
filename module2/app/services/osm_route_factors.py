"""OSM Overpass factors for lighting, road connectivity, and nearby safe places.

One corridor query covers sampled points along the route. Counts are turned
into 0–100 safety scores in the same band the rest of route_scorer expects.
"""
import logging
import math

import httpx

from app.config import settings
from app.services.geo import haversine, path_length

log = logging.getLogger("osm_route_factors")

# Highway classes used as a crude network-connectivity signal: more distinct
# intersecting ways and junctions along the corridor mean more ways to leave
# an unsafe stretch (not graph-theoretic betweenness).
_CONNECT_HIGHWAYS = (
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street", "service",
)
_JUNCTION_HIGHWAYS = (
    "crossing", "traffic_signals", "stop", "give_way", "mini_roundabout",
    "turning_circle", "motorway_junction",
)
# Same public/refuge classes as module1 safe_places / crime OSM features.
_SAFE_AMENITIES = {
    "police", "hospital", "fire_station", "pharmacy",
    "townhall", "courthouse",
}

_OSM_KEYS = ("lighting", "connectivity", "safe_locations")
_CACHE: dict[tuple, dict[str, int]] = {}
_PLACE_CACHE: dict[tuple, list] = {}
_CACHE_MAX = 48
_PLACE_LIMIT = 8


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(round(min(hi, max(lo, value))))


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coords(element: dict) -> tuple[float, float] | None:
    lat = _as_float(element.get("lat"))
    lon = _as_float(element.get("lon"))
    if lat is not None and lon is not None:
        return lat, lon
    center = element.get("center")
    if isinstance(center, dict):
        clat, clon = _as_float(center.get("lat")), _as_float(center.get("lon"))
        if clat is not None and clon is not None:
            return clat, clon
    return None


def sample_points(geom, max_points: int | None = None, min_spacing_m: float | None = None):
    """Evenly spaced points along the polyline, capped so Overpass stays small."""
    if not geom:
        return []
    max_points = max_points or settings.overpass_max_samples
    min_spacing_m = min_spacing_m or settings.overpass_sample_spacing_m
    points = [geom[0]]
    acc = 0.0
    for i in range(1, len(geom)):
        acc += haversine(geom[i - 1], geom[i])
        if acc >= min_spacing_m:
            points.append(geom[i])
            acc = 0.0
    if points[-1] != geom[-1]:
        points.append(geom[-1])
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    return [points[int(round(i * step))] for i in range(max_points)]


def _around_union(selector: str, samples) -> str:
    radius = settings.overpass_corridor_m
    parts = [f"{selector}(around:{radius},{lat},{lon})" for lat, lon in samples]
    return ";\n  ".join(parts)


def build_query(samples) -> str:
    timeout = settings.overpass_query_timeout_seconds
    around = _around_union
    body = ";\n  ".join((
        around('node["highway"="street_lamp"]', samples),
        around('node["lit"]', samples),
        around('way["lit"]', samples),
        around('way["highway"]["lit"]', samples),
        around('node["highway"~"crossing|traffic_signals|stop|give_way|mini_roundabout|turning_circle|motorway_junction"]', samples),
        around('node["junction"]', samples),
        around('way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service"]', samples),
        around('node["amenity"~"police|hospital|fire_station|pharmacy|townhall|courthouse"]', samples),
        around('way["amenity"~"police|hospital|fire_station|pharmacy|townhall|courthouse"]', samples),
        around('node["building"="public"]', samples),
        around('way["building"="public"]', samples),
        around('node["office"="government"]', samples),
        around('way["office"="government"]', samples),
        around('node["railway"="subway_entrance"]', samples),
        around('node["station"="subway"]', samples),
        around('node["subway"="yes"]', samples),
    ))
    return f"[out:json][timeout:{timeout}];\n(\n  {body};\n);\nout center;"


def _cache_key(samples) -> tuple:
    return tuple((round(lat, 4), round(lon, 4)) for lat, lon in samples)


def fetch_overpass_payload(query: str) -> dict:
    """POST an Overpass query. Raises on timeout, HTTP errors, or bad JSON."""
    headers = {"User-Agent": settings.http_user_agent, "Accept": "application/json"}
    timeout = httpx.Timeout(settings.overpass_timeout_seconds)
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.post(settings.overpass_url, data={"data": query})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass payload has no elements list.")
    return payload


def _is_lamp(tags: dict) -> bool:
    return tags.get("highway") == "street_lamp" or tags.get("light_source") == "lantern"


def _lit_value(tags: dict) -> str | None:
    lit = tags.get("lit")
    if isinstance(lit, str):
        return lit.strip().lower()
    return None


def _is_safe_place(tags: dict) -> bool:
    if tags.get("amenity") in _SAFE_AMENITIES:
        return True
    if tags.get("building") == "public" or tags.get("office") == "government":
        return True
    if tags.get("station") == "subway" or tags.get("railway") == "subway_entrance" or tags.get("subway") == "yes":
        return True
    return False


def _is_junction(tags: dict) -> bool:
    if tags.get("junction"):
        return True
    return tags.get("highway") in _JUNCTION_HIGHWAYS


def _is_connect_way(tags: dict) -> bool:
    return tags.get("highway") in _CONNECT_HIGHWAYS


def _min_distance_m(geom, points) -> float | None:
    if not geom or not points:
        return None
    best = None
    for plat, plon in points:
        for lat, lon in geom[:: max(1, len(geom) // 12)]:
            d = haversine((lat, lon), (plat, plon))
            if best is None or d < best:
                best = d
    return best


def _place_kind(tags: dict) -> str:
    amenity = tags.get("amenity")
    if amenity in _SAFE_AMENITIES:
        return amenity
    if tags.get("station") == "subway" or tags.get("railway") == "subway_entrance" or tags.get("subway") == "yes":
        return "transit"
    return "public"


def places_from_elements(elements: list, geom, limit: int = _PLACE_LIMIT) -> list[dict]:
    """Named OSM refuges near the geometry, nearest first."""
    found = []
    seen: set[tuple] = set()
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags")
        if not isinstance(tags, dict) or not _is_safe_place(tags):
            continue
        coords = _coords(element)
        if coords is None:
            continue
        kind = _place_kind(tags)
        key = (round(coords[0], 4), round(coords[1], 4), kind)
        if key in seen:
            continue
        seen.add(key)
        name = tags.get("name")
        if not isinstance(name, str) or not name.strip():
            name = kind.replace("_", " ").title()
        distance = _min_distance_m(geom, [coords]) if geom else None
        found.append({
            "name": name.strip(),
            "kind": kind,
            "latitude": coords[0],
            "longitude": coords[1],
            "distance_m": round(distance) if distance is not None else None,
        })
    found.sort(key=lambda place: place["distance_m"] if place["distance_m"] is not None else 1e12)
    return found[:limit]


def factors_from_elements(elements: list, geom) -> dict[str, int]:
    """Map Overpass elements to lighting / connectivity / safe_locations scores."""
    length_km = max(path_length(geom) / 1000.0, 0.2)
    lamps = 0
    lit_yes = 0
    lit_no = 0
    junctions = 0
    road_ids: set[object] = set()
    safe_n = 0
    safe_pts: list[tuple[float, float]] = []

    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags")
        if not isinstance(tags, dict):
            continue
        if _is_lamp(tags):
            lamps += 1
        lit = _lit_value(tags)
        if lit in {"yes", "24/7", "sunset-sunrise", "automatic"}:
            lit_yes += 1
        elif lit in {"no", "disused"}:
            lit_no += 1
        if _is_junction(tags):
            junctions += 1
        if _is_connect_way(tags):
            eid = element.get("id", id(element))
            road_ids.add(("way" if element.get("type") == "way" else "n", eid))
        if _is_safe_place(tags):
            safe_n += 1
            coords = _coords(element)
            if coords:
                safe_pts.append(coords)

    lamp_km = lamps / length_km
    # ~10 lamps/km or several lit=yes ways is a well-mapped urban street.
    lighting = 58 + min(lamp_km, 16) * 2.0 + min(lit_yes, 18) * 0.7 - min(lit_no, 12) * 1.6

    j_km = junctions / length_km
    r_km = len(road_ids) / length_km
    connectivity = 55 + min(j_km, 18) * 1.3 + min(r_km, 22) * 0.9

    nearest = _min_distance_m(geom, safe_pts)
    safe = 52 + min(safe_n, 10) * 3.2
    if nearest is not None:
        if nearest < 150:
            safe += 12
        elif nearest < 400:
            safe += 7
        elif nearest < 800:
            safe += 3
        else:
            safe -= min(8, math.log10(max(nearest, 1)) * 2)

    return {
        "lighting": _clamp(lighting, 40, 96),
        "connectivity": _clamp(connectivity, 40, 96),
        "safe_locations": _clamp(safe, 40, 96),
    }


def try_osm_factors(geom) -> dict[str, int] | None:
    """Return OSM factor scores, or None so the caller can fall back to the hash."""
    samples = sample_points(geom)
    if len(samples) < 1:
        return None
    key = _cache_key(samples)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        payload = fetch_overpass_payload(build_query(samples))
        elements = payload.get("elements") or []
        factors = factors_from_elements(elements, geom)
        places = places_from_elements(elements, geom)
    except Exception as exc:
        log.warning("OSM route factors unavailable (%s); using geometry hash fallback", type(exc).__name__)
        return None
    if len(_CACHE) >= _CACHE_MAX:
        oldest = next(iter(_CACHE))
        _CACHE.pop(oldest, None)
        _PLACE_CACHE.pop(oldest, None)
    _CACHE[key] = factors
    _PLACE_CACHE[key] = places
    return factors


def safe_places_for(geom) -> list[dict]:
    """Real OSM refuges along a route, or around a single point. Empty if Overpass fails."""
    samples = sample_points(geom)
    if len(samples) < 1:
        return []
    key = _cache_key(samples)
    cached = _PLACE_CACHE.get(key)
    if cached is not None:
        return cached
    try_osm_factors(geom)
    return list(_PLACE_CACHE.get(key) or [])


def clear_cache() -> None:
    _CACHE.clear()
    _PLACE_CACHE.clear()
