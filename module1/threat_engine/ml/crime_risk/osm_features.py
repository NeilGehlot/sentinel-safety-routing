"""OSM counts and police distance for a degree grid.

Counts are city-agnostic. Cell indexes are used only to join features.
They are not model inputs. This module does not call the network when
the caller skips it. A timeout or a bad payload returns None.
"""

import math
from dataclasses import dataclass

import httpx

from app.config import EARTH_RADIUS_M, OSM_FEATURE_TIMEOUT_SECONDS, OVERPASS_URL


@dataclass(frozen=True)
class OsmCellFeatures:
    """Per-cell counts. police_distance_m is None when no police point came back."""

    bar_count: dict[tuple[int, int], int]
    transit_count: dict[tuple[int, int], int]
    shop_count: dict[tuple[int, int], int]
    road_count: dict[tuple[int, int], int]
    police_distance_m: dict[tuple[int, int], float]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = EARTH_RADIUS_M
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    chord = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(chord)))


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _category(tags: dict[str, object]) -> str | None:
    amenity = tags.get("amenity")
    if amenity == "police":
        return "police"
    if amenity in {"bar", "pub", "nightclub"}:
        return "bar"
    if tags.get("railway") == "station" or tags.get("station") == "subway" or tags.get("subway") == "yes":
        return "transit"
    if tags.get("public_transport") in {"station", "stop_position"}:
        return "transit"
    if tags.get("highway") in {"primary", "secondary", "tertiary"}:
        return "road"
    if "shop" in tags:
        return "shop"
    return None


def fetch_osm_elements(
    south: float,
    west: float,
    north: float,
    east: float,
    timeout_seconds: float | None = None,
) -> list[dict[str, object]]:
    """POST one Overpass query. Raises on timeout or a bad payload."""
    timeout = OSM_FEATURE_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    query = f"""
[out:json][timeout:{max(1, int(timeout))}];
(
  node["amenity"="police"]({south},{west},{north},{east});
  node["amenity"="bar"]({south},{west},{north},{east});
  node["amenity"="pub"]({south},{west},{north},{east});
  node["amenity"="nightclub"]({south},{west},{north},{east});
  node["railway"="station"]({south},{west},{north},{east});
  node["station"="subway"]({south},{west},{north},{east});
  node["shop"]({south},{west},{north},{east});
  node["highway"~"primary|secondary|tertiary"]({south},{west},{north},{east});
);
out body;
"""
    headers = {"User-Agent": "threat-engine/0.1", "Accept": "application/json"}
    with httpx.Client(timeout=httpx.Timeout(timeout + 5.0), headers=headers) as client:
        response = client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass payload has no elements list.")
    elements = payload["elements"]
    return [item for item in elements if isinstance(item, dict)]


def features_from_elements(
    elements: list[dict[str, object]],
    cells: list[tuple[int, int]],
    bin_deg: float,
) -> OsmCellFeatures:
    """Count points into degree cells and measure distance from each cell center to police."""
    buckets: dict[str, dict[tuple[int, int], int]] = {
        "bar": {},
        "transit": {},
        "shop": {},
        "road": {},
    }
    police: list[tuple[float, float]] = []
    for element in elements:
        tags = element.get("tags")
        if not isinstance(tags, dict):
            continue
        lat = _as_float(element.get("lat"))
        lon = _as_float(element.get("lon"))
        if lat is None or lon is None:
            continue
        kind = _category(tags)
        if kind == "police":
            police.append((lat, lon))
            continue
        if kind not in buckets:
            continue
        key = (math.floor(lat / bin_deg), math.floor(lon / bin_deg))
        buckets[kind][key] = buckets[kind].get(key, 0) + 1
    distances: dict[tuple[int, int], float] = {}
    for cell in cells:
        center_lat = (cell[0] + 0.5) * bin_deg
        center_lon = (cell[1] + 0.5) * bin_deg
        if not police:
            continue
        distances[cell] = min(_haversine_m(center_lat, center_lon, plat, plon) for plat, plon in police)
    return OsmCellFeatures(
        bar_count=buckets["bar"],
        transit_count=buckets["transit"],
        shop_count=buckets["shop"],
        road_count=buckets["road"],
        police_distance_m=distances,
    )


def try_osm_features(
    south: float,
    west: float,
    north: float,
    east: float,
    cells: list[tuple[int, int]],
    bin_deg: float,
) -> tuple[OsmCellFeatures | None, str]:
    """Fetch OSM features. On failure return None and the error text. Never raise."""
    try:
        elements = fetch_osm_elements(south, west, north, east)
        return features_from_elements(elements, cells, bin_deg), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
