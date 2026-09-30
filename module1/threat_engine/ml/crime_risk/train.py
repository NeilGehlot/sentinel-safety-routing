"""Train the cell-hour incident model with a temporal split and a spatial holdout.

No random split. This pipeline is trained on Los Angeles data to demonstrate
the method. Features are city-agnostic and ready for local police data.
Gurugram output is illustrative, not validated.
"""

import json
import os
from pathlib import Path

import lightgbm as lgb
import numpy as np

from app.config import (
    CRIME_MODEL_BIN_DEG,
    CRIME_MODEL_META_PATH,
    CRIME_MODEL_MIN_CELL_INCIDENTS,
    CRIME_MODEL_PATH,
    CRIME_MODEL_SPATIAL_LAT_QUANTILE,
    CRIME_MODEL_TEST_YEAR,
)
from ml.crime_risk.evaluate import (
    calibration_points,
    cell_hour_rates,
    comparison_line,
    format_metric,
    pr_auc,
    write_calibration_svg,
    write_report,
)
from ml.crime_risk.osm_features import try_osm_features
from ml.crime_risk.prepare_data import (
    DISCLAIMER,
    IncidentTable,
    bin_index,
    calendar_arrays,
    download_lapd,
    hour_index,
    load_incidents,
    panel_hours,
)

TIME_FEATURES = ("hour", "dow", "month")
LAG_FEATURES = ("lag_cell_1h", "lag_cell_24h", "lag_cell_168h", "lag_neighbor_1h")
OSM_FEATURES = (
    "osm_bar_count",
    "osm_transit_count",
    "osm_shop_count",
    "osm_road_count",
    "police_distance_m",
)
NEIGHBOR_SHIFTS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def _default_csv() -> Path:
    configured = os.getenv("LAPD_CSV", "/tmp/lapd/incidents.csv")
    return Path(configured)


def _counts(table: IncidentTable, bin_deg: float) -> dict[tuple[int, int, int], int]:
    counts: dict[tuple[int, int, int], int] = {}
    for lat, lon, year, month, day, hour in zip(
        table.lat, table.lon, table.year, table.month, table.day, table.hour
    ):
        index = hour_index(int(year), int(month), int(day), int(hour))
        if index is None:
            continue
        key = (bin_index(float(lat), bin_deg), bin_index(float(lon), bin_deg), index)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _active_cells(counts: dict[tuple[int, int, int], int], minimum: int) -> list[tuple[int, int]]:
    totals: dict[tuple[int, int], int] = {}
    for (cell_i, cell_j, _hour), count in counts.items():
        key = (cell_i, cell_j)
        totals[key] = totals.get(key, 0) + count
    kept = [key for key, total in totals.items() if total >= minimum]
    kept.sort()
    return kept


def _holdout_cells(cells: list[tuple[int, int]], quantile: float) -> set[tuple[int, int]]:
    lats = sorted(cell[0] for cell in cells)
    if not lats:
        return set()
    position = min(len(lats) - 1, max(0, int(quantile * (len(lats) - 1))))
    cutoff = lats[position]
    return {cell for cell in cells if cell[0] >= cutoff}


def _fill_lags(
    counts: dict[tuple[int, int, int], int],
    cell_pos: dict[tuple[int, int], int],
    n_hours: int,
    lag1: np.ndarray,
    lag24: np.ndarray,
    lag168: np.ndarray,
    lag_neighbor: np.ndarray,
) -> None:
    for (cell_i, cell_j, hour_at), count in counts.items():
        position = cell_pos.get((cell_i, cell_j))
        if position is not None:
            base = position * n_hours
            if hour_at + 1 < n_hours:
                lag1[base + hour_at + 1] = count
            if hour_at + 24 < n_hours:
                lag24[base + hour_at + 24] = count
            if hour_at + 168 < n_hours:
                lag168[base + hour_at + 168] = count
        if hour_at + 1 >= n_hours:
            continue
        for shift_i, shift_j in NEIGHBOR_SHIFTS:
            neighbor = cell_pos.get((cell_i + shift_i, cell_j + shift_j))
            if neighbor is None:
                continue
            lag_neighbor[neighbor * n_hours + hour_at + 1] += count


def _matrix(
    cells: list[tuple[int, int]],
    counts: dict[tuple[int, int, int], int],
    osm_columns: dict[str, np.ndarray] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    n_hours = panel_hours()
    n_cells = len(cells)
    n_rows = n_cells * n_hours
    hour, dow, month, year = calendar_arrays()
    names = list(TIME_FEATURES + LAG_FEATURES)
    if osm_columns is not None:
        names.extend(OSM_FEATURES)
    features = np.zeros((n_rows, len(names)), dtype=np.float32)
    labels = np.zeros(n_rows, dtype=np.int8)
    years = np.empty(n_rows, dtype=np.int16)
    cell_of_row = np.empty(n_rows, dtype=np.int32)
    for position, _cell in enumerate(cells):
        start = position * n_hours
        stop = start + n_hours
        features[start:stop, 0] = hour
        features[start:stop, 1] = dow
        features[start:stop, 2] = month
        years[start:stop] = year
        cell_of_row[start:stop] = position
        if osm_columns is not None:
            for column, values in enumerate(osm_columns.values(), start=3 + len(LAG_FEATURES)):
                features[start:stop, column] = values[position]
    cell_pos = {cell: index for index, cell in enumerate(cells)}
    lag1 = features[:, 3]
    lag24 = features[:, 4]
    lag168 = features[:, 5]
    lag_neighbor = features[:, 6]
    _fill_lags(counts, cell_pos, n_hours, lag1, lag24, lag168, lag_neighbor)
    for (cell_i, cell_j, hour_at), count in counts.items():
        position = cell_pos.get((cell_i, cell_j))
        if position is None or count <= 0:
            continue
        labels[position * n_hours + hour_at] = 1
    return features, labels, years, names


def _osm_columns(
    cells: list[tuple[int, int]],
    table: IncidentTable,
    bin_deg: float,
) -> tuple[dict[str, np.ndarray] | None, str]:
    south = float(np.min(table.lat))
    north = float(np.max(table.lat))
    west = float(np.min(table.lon))
    east = float(np.max(table.lon))
    osm, error = try_osm_features(south, west, north, east, cells, bin_deg)
    if osm is None:
        return None, error or "OSM features were not available."
    def _count(mapping: dict[tuple[int, int], int]) -> np.ndarray:
        return np.asarray([mapping.get(cell, 0) for cell in cells], dtype=np.float32)

    distance = np.asarray(
        [osm.police_distance_m.get(cell, np.nan) for cell in cells],
        dtype=np.float32,
    )
    if np.isnan(distance).any():
        fill = float(np.nanmax(distance)) if np.isfinite(distance).any() else 0.0
        distance = np.where(np.isnan(distance), fill, distance)
    columns = {
        "osm_bar_count": _count(osm.bar_count),
        "osm_transit_count": _count(osm.transit_count),
        "osm_shop_count": _count(osm.shop_count),
        "osm_road_count": _count(osm.road_count),
        "police_distance_m": distance.astype(np.float32),
    }
    return columns, ""


def _indices(cell_positions: list[int], hour_indexes: np.ndarray, n_hours: int) -> np.ndarray:
    blocks = [position * n_hours + hour_indexes for position in cell_positions]
    if not blocks:
        return np.empty(0, dtype=np.int64)
    return np.concatenate(blocks)


def train(csv_path: Path | None = None) -> dict[str, object]:
    """Fit the model and write the report. Returns the computed summary."""
    source = csv_path or _default_csv()
    if not source.is_file():
        download_lapd(source)
    table = load_incidents(source)
    bin_deg = CRIME_MODEL_BIN_DEG
    counts = _counts(table, bin_deg)
    cells = _active_cells(counts, CRIME_MODEL_MIN_CELL_INCIDENTS)
    if len(cells) < 4:
        raise RuntimeError("Not enough occupied cells to train.")
    holdout = _holdout_cells(cells, CRIME_MODEL_SPATIAL_LAT_QUANTILE)
    osm_columns, osm_error = _osm_columns(cells, table, bin_deg)
    features, labels, years, names = _matrix(cells, counts, osm_columns)
    n_hours = panel_hours()
    test_year = CRIME_MODEL_TEST_YEAR
    train_cells = [index for index, cell in enumerate(cells) if cell not in holdout]
    holdout_cells = [index for index, cell in enumerate(cells) if cell in holdout]
    train_hours = np.flatnonzero(years[:n_hours] < test_year)
    test_hours = np.flatnonzero(years[:n_hours] == test_year)
    train_idx = _indices(train_cells, train_hours, n_hours)
    temporal_idx = _indices(train_cells, test_hours, n_hours)
    spatial_train_idx = _indices(holdout_cells, train_hours, n_hours)
    spatial_test_idx = _indices(holdout_cells, test_hours, n_hours)
    positive = float(labels[train_idx].sum())
    negative = float(len(train_idx) - positive)
    params = {
        "objective": "binary",
        "verbosity": -1,
        "deterministic": True,
        "seed": 0,
        "feature_fraction": 1.0,
        "bagging_fraction": 1.0,
        "num_threads": 1,
        "scale_pos_weight": negative / max(positive, 1.0),
    }
    dataset = lgb.Dataset(
        features[train_idx],
        label=labels[train_idx],
        feature_name=names,
        free_raw_data=False,
    )
    booster = lgb.train(params, dataset, num_boost_round=80)
    model_path = Path(CRIME_MODEL_PATH)
    meta_path = Path(CRIME_MODEL_META_PATH)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_path))
    train_proba = booster.predict(features[train_idx])
    percentile_edges = np.quantile(train_proba, np.linspace(0.0, 1.0, 1001)).astype(float).tolist()
    temporal_proba = booster.predict(features[temporal_idx])
    temporal_y = labels[temporal_idx]
    hour_of_day = features[temporal_idx, 0].astype(np.int16)
    cell_of_temporal = np.empty(len(temporal_idx), dtype=np.int32)
    cursor = 0
    for position in train_cells:
        cell_of_temporal[cursor : cursor + len(test_hours)] = position
        cursor += len(test_hours)
    train_hour_of_day = features[train_idx, 0].astype(np.int16)
    cell_of_train = np.empty(len(train_idx), dtype=np.int32)
    cursor = 0
    for position in train_cells:
        cell_of_train[cursor : cursor + len(train_hours)] = position
        cursor += len(train_hours)
    rates = cell_hour_rates(labels[train_idx], cell_of_train, train_hour_of_day, len(cells))
    baseline = rates[cell_of_temporal, hour_of_day]
    model_auc = pr_auc(temporal_y, temporal_proba)
    baseline_auc = pr_auc(temporal_y, baseline)
    spatial_train_auc = pr_auc(labels[spatial_train_idx], booster.predict(features[spatial_train_idx]))
    spatial_test_auc = pr_auc(labels[spatial_test_idx], booster.predict(features[spatial_test_idx]))
    predicted, observed = calibration_points(temporal_y, temporal_proba)
    reports = Path(__file__).resolve().parents[1] / "reports"
    svg_path = reports / "crime_risk_calibration.svg"
    report_path = reports / "crime_risk_report.md"
    write_calibration_svg(svg_path, predicted, observed)
    meta = {
        "disclaimer": DISCLAIMER,
        "training_city": "Los Angeles",
        "source": "LAPD Crime Data from 2020 to Present",
        "bin_deg": bin_deg,
        "features": names,
        "percentile_edges": percentile_edges,
        "osm_used": osm_columns is not None,
        "test_year": test_year,
        "illustrative_outside_training_city": True,
    }
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    prevalence = float(temporal_y.mean()) if len(temporal_y) else 0.0
    sections = [
        (
            "Data",
            [
                "- Source: LAPD Crime Data from 2020 to Present (Socrata 2nrs-mtv8). Not NCRB.",
                f"- Rows read: {table.rows_read}. Rows kept after geocode and hour checks: {table.rows_kept}.",
                f"- Grid: {bin_deg} degrees. Cells with at least {CRIME_MODEL_MIN_CELL_INCIDENTS} incidents: {len(cells)}.",
                f"- Panel rows: {len(labels)}. Positive hours in the training slice: {int(positive)}.",
                f"- OSM features used: {osm_columns is not None}.",
                f"- OSM note: {osm_error or 'OSM counts and police distance were joined onto cells.'}",
            ],
        ),
        (
            "Split",
            [
                f"- Temporal train: years before {test_year}, excluding the northern spatial holdout.",
                f"- Temporal test: {test_year} in the same cells. No random split.",
                f"- Spatial holdout: cells at or above lat-bin quantile {CRIME_MODEL_SPATIAL_LAT_QUANTILE} "
                f"({len(holdout)} cells). Those cells are absent from training.",
            ],
        ),
        (
            "Metrics",
            [
                f"- Temporal test prevalence (share of cell-hours with an incident): {prevalence:.6f}.",
                f"- Model PR-AUC on the temporal test: {format_metric(model_auc)}.",
                f"- Baseline PR-AUC (training-period average for that cell and hour): {format_metric(baseline_auc)}.",
                f"- {comparison_line(model_auc, baseline_auc)}",
                f"- Spatial holdout PR-AUC on years before {test_year}: {format_metric(spatial_train_auc)}.",
                f"- Spatial holdout PR-AUC in {test_year}: {format_metric(spatial_test_auc)}.",
                "- The cell-hour baseline is only scored on the temporal test, where those cells were seen in earlier years.",
            ],
        ),
        (
            "Calibration",
            [
                f"- Quantile calibration curve: {svg_path.name}.",
                "- " + DISCLAIMER,
            ],
        ),
    ]
    write_report(report_path, sections)
    return {
        "model_auc": model_auc,
        "baseline_auc": baseline_auc,
        "spatial_train_auc": spatial_train_auc,
        "spatial_test_auc": spatial_test_auc,
        "osm_used": osm_columns is not None,
        "osm_error": osm_error,
        "report": str(report_path),
        "model": str(model_path),
    }


def main() -> None:
    summary = train()
    print(json.dumps({key: summary[key] for key in summary if key != "percentile_edges"}))


if __name__ == "__main__":
    main()
