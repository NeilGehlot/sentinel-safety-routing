"""Crime risk from a LightGBM artifact.

When the artifact is missing, this does not read a city table. Outside mock
mode it blends OSM feature counts with the time-of-day curve. If that cannot
be read, the signal is unavailable and the score is renormalized.

Pipeline trained on LA data to demonstrate the method, city-agnostic
features, ready for local police data. Gurugram output is illustrative,
not validated.
"""

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from cachetools import TTLCache

from app import config
from app.config import (
    CRIME_GRID_BIN_DEG,
    CRIME_GRID_CACHE_TTL_SECONDS,
    CRIME_GRID_PATH,
    CRIME_MODEL_META_PATH,
    CRIME_MODEL_PATH,
    DEFAULT_CRIME_GRID_PATH,
)
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest

_GRID_CACHE: TTLCache[str, dict[tuple[float, float], float]] = TTLCache(
    maxsize=4,
    ttl=CRIME_GRID_CACHE_TTL_SECONDS,
)
_MODEL_CACHE: dict[str, "_LoadedModel"] = {}

_LAG_FEATURES = ("lag_cell_1h", "lag_cell_24h", "lag_cell_168h", "lag_neighbor_1h")
_OSM_FEATURES = {
    "osm_bar_count",
    "osm_transit_count",
    "osm_shop_count",
    "osm_road_count",
    "police_distance_m",
}


@dataclass
class _LoadedModel:
    """Booster plus the training percentile edges. Not a city identifier."""

    booster: object
    features: list[str]
    edges: np.ndarray
    bin_deg: float
    explainer: object | None = None


def reset_model_cache() -> None:
    """Drop a loaded booster so tests can swap the artifact path."""
    _MODEL_CACHE.clear()


def grid_path() -> Path | None:
    """Resolve the configured CSV, or the packaged file when the default path is used."""
    configured = Path(CRIME_GRID_PATH)
    if configured.is_file():
        return configured
    if CRIME_GRID_PATH == DEFAULT_CRIME_GRID_PATH:
        packaged = Path(__file__).resolve().parents[1] / "data" / "crime_grid.csv"
        if packaged.is_file():
            return packaged
    return None


def _bin(coord: float) -> float:
    size = CRIME_GRID_BIN_DEG
    return round(math.floor(coord / size) * size, 6)


def _load_grid(path: Path) -> dict[tuple[float, float], float] | None:
    key = str(path.resolve())
    cached = _GRID_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        rows: dict[tuple[float, float], float] = {}
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                lat_bin = round(float(row["lat_bin"]), 6)
                lon_bin = round(float(row["lon_bin"]), 6)
                rows[(lat_bin, lon_bin)] = float(row["crime_index"])
    except Exception:
        return None
    _GRID_CACHE[key] = rows
    return rows


def _from_grid(request: AssessRequest) -> SignalResult:
    """Old cell table. signal() does not call this and does not read a city CSV."""
    try:
        location = request.location
        if location is None:
            return unavailable("crime_risk", "Location is missing.")
        path = grid_path()
        if path is None:
            return unavailable("crime_risk", "Crime grid file is missing.")
        grid = _load_grid(path)
        if grid is None:
            return unavailable("crime_risk", "Crime grid could not be read.")
        found = grid.get((_bin(location.lat), _bin(location.lon)))
        if found is None:
            return unavailable("crime_risk", "Crime grid has no value for this location.")
        risk = clamp_risk(found)
        return SignalResult(
            name="crime_risk",
            risk=risk,
            reason=f"the synthetic crime grid index here is {risk:.2f}",
            available=True,
            details={"crime_index": risk},
        )
    except Exception:
        return unavailable("crime_risk", "Crime grid could not be read.")


def _load_model() -> _LoadedModel | None:
    model_path = Path(CRIME_MODEL_PATH)
    meta_path = Path(CRIME_MODEL_META_PATH)
    if not model_path.is_file() or not meta_path.is_file():
        return None
    key = f"{model_path.resolve()}|{meta_path.stat().st_mtime_ns}|{model_path.stat().st_mtime_ns}"
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    import lightgbm as lgb

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    features = meta.get("features")
    edges = meta.get("percentile_edges")
    if not isinstance(features, list) or not features or not all(isinstance(name, str) for name in features):
        return None
    if not isinstance(edges, list) or len(edges) < 2:
        return None
    booster = lgb.Booster(model_file=str(model_path))
    loaded = _LoadedModel(
        booster=booster,
        features=list(features),
        edges=np.asarray(edges, dtype=np.float64),
        bin_deg=float(meta.get("bin_deg") or config.CRIME_MODEL_BIN_DEG),
    )
    _MODEL_CACHE.clear()
    _MODEL_CACHE[key] = loaded
    return loaded


def _percentile_rank(probability: float, edges: np.ndarray) -> float:
    """Share of training probabilities at or below this one. Clamped to 0..1."""
    index = int(np.searchsorted(edges, probability, side="right"))
    rank = index / float(len(edges) - 1)
    return clamp_risk(rank)


def _osm_values(lat: float, lon: float, bin_deg: float) -> dict[str, float] | None:
    """Counts for this cell. None when the fetch fails or police distance is unknown."""
    from ml.crime_risk.osm_features import try_osm_features
    from ml.crime_risk.prepare_data import bin_index

    cell_i = bin_index(lat, bin_deg)
    cell_j = bin_index(lon, bin_deg)
    south = cell_i * bin_deg
    west = cell_j * bin_deg
    osm, _error = try_osm_features(south, west, south + bin_deg, west + bin_deg, [(cell_i, cell_j)], bin_deg)
    if osm is None:
        return None
    cell = (cell_i, cell_j)
    distance = osm.police_distance_m.get(cell)
    if distance is None:
        return None
    return {
        "osm_bar_count": float(osm.bar_count.get(cell, 0)),
        "osm_transit_count": float(osm.transit_count.get(cell, 0)),
        "osm_shop_count": float(osm.shop_count.get(cell, 0)),
        "osm_road_count": float(osm.road_count.get(cell, 0)),
        "police_distance_m": float(distance),
    }


def _feature_row(request: AssessRequest, loaded: _LoadedModel) -> np.ndarray | None:
    location = request.location
    timestamp = request.timestamp
    if location is None or timestamp is None:
        return None
    values: dict[str, float] = {
        "hour": float(timestamp.hour),
        "dow": float(timestamp.weekday()),
        "month": float(timestamp.month),
    }
    for name in _LAG_FEATURES:
        values[name] = 0.0
    if any(name in _OSM_FEATURES for name in loaded.features):
        osm_values = _osm_values(location.lat, location.lon, loaded.bin_deg)
        if osm_values is None:
            return None
        values.update(osm_values)
    row: list[float] = []
    for name in loaded.features:
        if name not in values:
            return None
        row.append(values[name])
    return np.asarray([row], dtype=np.float32)


def _positive_shap(values: object) -> np.ndarray | None:
    if isinstance(values, list):
        if not values:
            return None
        values = values[-1]
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return None
    if array.ndim == 2:
        array = array[0]
    if array.ndim != 1:
        return None
    return array


def _shap_top(loaded: _LoadedModel, row: np.ndarray) -> list[str] | None:
    import shap

    if loaded.explainer is None:
        loaded.explainer = shap.TreeExplainer(loaded.booster)
    values = loaded.explainer.shap_values(row)
    array = _positive_shap(values)
    if array is None or array.size != len(loaded.features):
        return None
    order = np.argsort(-np.abs(array))
    picked = [loaded.features[int(index)] for index in order[:2]]
    if len(picked) < min(2, len(loaded.features)):
        return None
    return picked


def _outside_training_city(lat: float, lon: float) -> bool:
    from ml.crime_risk.prepare_data import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN

    return not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX)


def _from_model(request: AssessRequest) -> SignalResult | None:
    """Percentile risk and a SHAP reason. None sends the caller back to the grid."""
    try:
        loaded = _load_model()
        if loaded is None:
            return None
        row = _feature_row(request, loaded)
        if row is None:
            return None
        probability = float(loaded.booster.predict(row)[0])
        risk = _percentile_rank(probability, loaded.edges)
        top = _shap_top(loaded, row)
        if not top:
            return None
        from ml.crime_risk.prepare_data import DISCLAIMER

        if len(top) == 1:
            lead = f"SHAP ranks {top[0]} highest."
        else:
            lead = f"SHAP ranks {top[0]} and {top[1]} highest."
        location = request.location
        illustrative = True
        if location is not None:
            illustrative = _outside_training_city(location.lat, location.lon)
        return SignalResult(
            name="crime_risk",
            risk=risk,
            reason=f"{lead} {DISCLAIMER}",
            available=True,
            details={
                "probability": probability,
                "crime_index": risk,
                "illustrative": illustrative,
            },
        )
    except Exception:
        return None


def _area_fallback(request: AssessRequest) -> SignalResult | None:
    """OSM counts plus the time-of-day curve. None leaves crime unavailable."""
    location = request.location
    if location is None or request.timestamp is None:
        return None
    from app.providers.time_of_day import clock_hour, risk_for_hour

    counts = _osm_values(location.lat, location.lon, config.CRIME_MODEL_BIN_DEG)
    if counts is None:
        return None
    busy = (
        counts["osm_bar_count"]
        + counts["osm_transit_count"]
        + counts["osm_shop_count"]
        + counts["osm_road_count"]
    ) / 12.0
    if busy > 1.0:
        busy = 1.0
    police = counts["police_distance_m"] / 1500.0
    if police > 1.0:
        police = 1.0
    clock = risk_for_hour(clock_hour(request.timestamp))
    risk = clamp_risk((0.5 * busy) + (0.2 * police) + (0.3 * clock))
    return SignalResult(
        name="crime_risk",
        risk=risk,
        reason="area features and the time of day stand in because the crime model is not loaded",
        available=True,
        details={"crime_index": risk},
    )


def signal(request: AssessRequest) -> SignalResult:
    """Use the model when it loads. Never read a city CSV. Never raise."""
    try:
        if not config.MOCK_MODE:
            modeled = _from_model(request)
            if modeled is not None:
                return modeled
            rough = _area_fallback(request)
            if rough is not None:
                return rough
        return unavailable("crime_risk", "Crime risk is unavailable for this spot.")
    except Exception:
        return unavailable("crime_risk", "Crime risk could not be read.")
