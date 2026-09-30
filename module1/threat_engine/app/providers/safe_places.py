"""Nearest police, hospital, metro, or public building.

Mock mode keeps the fixed distance. Live mode queries OSM Overpass, caches one
result per 1 km cell, and times out instead of hanging. Failure returns
available=False and does not raise. Risk is clamp(distance_m / 1500). The
close-range negative stays in scoring and config.
"""

import math
from dataclasses import dataclass

from cachetools import TTLCache
import httpx

from app import config
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest


@dataclass(frozen=True)
class NearbyPlace:
    """A mapped place. name comes from OSM tags, not from a guessed landmark."""

    name: str
    distance_m: float
    direction: str


_CACHE: TTLCache[tuple[int, int], NearbyPlace] = TTLCache(
    maxsize=128,
    ttl=config.OVERPASS_CACHE_TTL_SECONDS,
)

_COMPASS: tuple[str, ...] = (
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
)


def clear_cache() -> None:
    """Drop cached places. Tests use this so calls do not leak."""
    _CACHE.clear()


def _meters_per_degree(lat: float) -> tuple[float, float]:
    per_lat = 2.0 * math.pi * config.EARTH_RADIUS_M / 360.0
    per_lon = per_lat * math.cos(math.radians(lat))
    return per_lat, per_lon


def cell_key(lat: float, lon: float) -> tuple[int, int]:
    """Floor the point into a 1 km cell."""
    per_lat, per_lon = _meters_per_degree(lat)
    size = float(config.SAFE_PLACES_CACHE_CELL_M)
    return (math.floor(lat * per_lat / size), math.floor(lon * per_lon / size))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    radius = config.EARTH_RADIUS_M
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    chord = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(chord)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees, 0 at north and 90 at east."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    east = math.sin(d_lon) * math.cos(phi2)
    north = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lon)
    return (math.degrees(math.atan2(east, north)) + 360.0) % 360.0


def compass(bearing: float) -> str:
    """Eight-point compass label for a bearing."""
    index = round(bearing / 45.0) % 8
    return _COMPASS[index]


def _place_name(tags: dict[str, object]) -> str:
    named = tags.get("name")
    if isinstance(named, str) and named.strip():
        return named.strip()
    amenity = tags.get("amenity")
    if amenity == "police":
        return "police station"
    if amenity == "hospital":
        return "hospital"
    if amenity == "townhall" or amenity == "courthouse" or tags.get("office") == "government":
        return "public building"
    if tags.get("building") == "public":
        return "public building"
    if tags.get("station") == "subway" or tags.get("railway") == "subway_entrance" or tags.get("subway") == "yes":
        return "metro station"
    return "safe place"


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _coords(element: dict[str, object]) -> tuple[float, float] | None:
    lat = _as_float(element.get("lat"))
    lon = _as_float(element.get("lon"))
    if lat is not None and lon is not None:
        return lat, lon
    center = element.get("center")
    if isinstance(center, dict):
        center_lat = _as_float(center.get("lat"))
        center_lon = _as_float(center.get("lon"))
        if center_lat is not None and center_lon is not None:
            return center_lat, center_lon
    return None


def _query(lat: float, lon: float) -> str:
    radius = config.OVERPASS_SEARCH_RADIUS_M
    timeout = config.OVERPASS_QUERY_TIMEOUT_SECONDS
    around = f"(around:{radius},{lat},{lon})"
    selectors = (
        f'node["amenity"="police"]{around}',
        f'way["amenity"="police"]{around}',
        f'node["amenity"="hospital"]{around}',
        f'way["amenity"="hospital"]{around}',
        f'node["railway"="subway_entrance"]{around}',
        f'way["railway"="subway_entrance"]{around}',
        f'node["station"="subway"]{around}',
        f'way["station"="subway"]{around}',
        f'node["subway"="yes"]{around}',
        f'way["subway"="yes"]{around}',
        f'node["building"="public"]{around}',
        f'way["building"="public"]{around}',
        f'node["amenity"="townhall"]{around}',
        f'way["amenity"="townhall"]{around}',
        f'node["amenity"="courthouse"]{around}',
        f'way["amenity"="courthouse"]{around}',
        f'node["office"="government"]{around}',
        f'way["office"="government"]{around}',
    )
    body = ";\n  ".join(selectors)
    return f"[out:json][timeout:{timeout}];\n(\n  {body};\n);\nout center;"


def fetch_overpass_payload(lat: float, lon: float) -> dict[str, object]:
    """POST an Overpass query. Raises on timeout, HTTP errors, or bad JSON."""
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept": "application/json"}
    timeout = httpx.Timeout(config.OVERPASS_TIMEOUT_SECONDS)
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.post(config.OVERPASS_URL, data={"data": _query(lat, lon)})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Overpass payload was not an object.")
    return payload


def nearest_place(lat: float, lon: float, payload: dict[str, object]) -> NearbyPlace | None:
    """Pick the closest element that has coordinates."""
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise ValueError("Overpass payload has no elements list.")
    best: NearbyPlace | None = None
    for element in elements:
        if not isinstance(element, dict):
            continue
        coords = _coords(element)
        if coords is None:
            continue
        place_lat, place_lon = coords
        distance = haversine_m(lat, lon, place_lat, place_lon)
        tags = element.get("tags")
        name = _place_name(tags if isinstance(tags, dict) else {})
        direction = compass(bearing_deg(lat, lon, place_lat, place_lon))
        candidate = NearbyPlace(name=name, distance_m=distance, direction=direction)
        if best is None or candidate.distance_m < best.distance_m:
            best = candidate
    return best


def _from_place(place: NearbyPlace) -> SignalResult:
    if place.distance_m < 0 or config.SAFE_PLACES_RISK_DISTANCE_M <= 0:
        return unavailable("safe_places", "Safe place distance is missing.")
    risk = clamp_risk(place.distance_m / config.SAFE_PLACES_RISK_DISTANCE_M)
    rounded = round(place.distance_m)
    return SignalResult(
        name="safe_places",
        risk=risk,
        reason=f"{place.name} is about {rounded} m {place.direction}",
        available=True,
        details={
            "distance_m": place.distance_m,
            "label": place.name,
            "direction": place.direction,
        },
    )


def _live(lat: float, lon: float) -> SignalResult:
    key = cell_key(lat, lon)
    cached = _CACHE.get(key)
    if cached is not None:
        return _from_place(cached)
    try:
        payload = fetch_overpass_payload(lat, lon)
        place = nearest_place(lat, lon, payload)
    except httpx.TimeoutException:
        return unavailable("safe_places", "Safe place lookup timed out.")
    except Exception:
        return unavailable("safe_places", "Safe place lookup failed.")
    if place is None:
        return unavailable("safe_places", "Safe place lookup returned no mapped place.")
    _CACHE[key] = place
    return _from_place(place)


def _mock() -> SignalResult:
    distance_m = config.MOCK_SAFE_PLACE_DISTANCE_M
    if distance_m < 0 or config.SAFE_PLACES_RISK_DISTANCE_M <= 0:
        return unavailable("safe_places", "Safe place distance is missing.")
    risk = clamp_risk(distance_m / config.SAFE_PLACES_RISK_DISTANCE_M)
    rounded = round(distance_m)
    return SignalResult(
        name="safe_places",
        risk=risk,
        reason=f"the nearest safe place is about {rounded} m away",
        available=True,
        details={"distance_m": distance_m, "label": config.MOCK_SAFE_PLACE_LABEL},
    )


def signal(request: AssessRequest) -> SignalResult:
    """Mock when MOCK_MODE is on. Otherwise query Overpass and never raise."""
    try:
        location = request.location
        if location is None:
            return unavailable("safe_places", "Location is missing.")
        if config.MOCK_MODE:
            return _mock()
        return _live(location.lat, location.lon)
    except Exception:
        return unavailable("safe_places", "Safe place distance could not be read.")
