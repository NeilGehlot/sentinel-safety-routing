"""Crime model fallback. MOCK_MODE stays on the synthetic grid."""

import json
from pathlib import Path

import numpy as np
import pytest

from app import config
from app.providers import crime_risk
from app.schemas import AssessRequest, Location
from ml.crime_risk.prepare_data import DISCLAIMER

IST_SAMPLE = {
    "session_id": "abc",
    "timestamp": "2026-09-29T23:40:00+05:30",
    "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
    "device": {"battery_pct": 18, "cellular_dbm": -108, "internet_available": False},
    "nearby_devices": {"ble_count": 3, "wifi_count": 2},
    "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
}


def _sample() -> AssessRequest:
    return AssessRequest.model_validate(IST_SAMPLE)


def _tiny_artifact(directory: Path, feature_names: list[str]) -> None:
    import lightgbm as lgb

    rows = np.array(
        [
            [0, 0, 100.0],
            [1, 0, 100.0],
            [12, 1, 400.0],
            [23, 5, 800.0],
            [8, 0, 200.0],
            [18, 3, 50.0],
        ],
        dtype=np.float32,
    )
    used = rows[:, : len(feature_names)]
    labels = np.array([0, 0, 1, 1, 0, 1])
    dataset = lgb.Dataset(used, label=labels, feature_name=feature_names)
    booster = lgb.train(
        {
            "objective": "binary",
            "verbosity": -1,
            "min_data_in_leaf": 1,
            "min_data_in_bin": 1,
            "deterministic": True,
            "seed": 0,
            "num_threads": 1,
        },
        dataset,
        num_boost_round=5,
    )
    booster.save_model(str(directory / "crime_risk.txt"))
    probabilities = booster.predict(used)
    edges = np.quantile(probabilities, np.linspace(0.0, 1.0, 1001)).astype(float).tolist()
    meta = {
        "features": feature_names,
        "percentile_edges": edges,
        "osm_used": "police_distance_m" in feature_names,
        "bin_deg": 0.05,
        "disclaimer": DISCLAIMER,
    }
    (directory / "crime_risk_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _point_at_artifact(monkeypatch: pytest.MonkeyPatch, directory: Path, mock_mode: bool) -> None:
    monkeypatch.setattr(config, "MOCK_MODE", mock_mode)
    monkeypatch.setattr(crime_risk, "CRIME_MODEL_PATH", str(directory / "crime_risk.txt"))
    monkeypatch.setattr(crime_risk, "CRIME_MODEL_META_PATH", str(directory / "crime_risk_meta.json"))
    crime_risk.reset_model_cache()


def test_missing_artifact_falls_back_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MOCK_MODE", False)
    monkeypatch.setattr(crime_risk, "CRIME_MODEL_PATH", "/tmp/crime-risk-missing.txt")
    monkeypatch.setattr(crime_risk, "CRIME_MODEL_META_PATH", "/tmp/crime-risk-missing.json")
    crime_risk.reset_model_cache()
    result = crime_risk.signal(_sample())
    assert result.available is True
    assert result.risk == pytest.approx(0.82)
    assert 0.0 <= result.risk <= 1.0


def test_broken_artifact_falls_back_without_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "crime_risk.txt").write_text("not a lightgbm model", encoding="utf-8")
    (tmp_path / "crime_risk_meta.json").write_text("{", encoding="utf-8")
    _point_at_artifact(monkeypatch, tmp_path, mock_mode=False)
    result = crime_risk.signal(_sample())
    assert result.available is True
    assert result.risk == pytest.approx(0.82)


def test_loaded_model_returns_shap_reason_and_unit_risk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    names = ["hour", "lag_cell_1h"]
    _tiny_artifact(tmp_path, names)
    _point_at_artifact(monkeypatch, tmp_path, mock_mode=False)
    result = crime_risk.signal(_sample())
    assert result.available is True
    assert 0.0 <= result.risk <= 1.0
    assert "SHAP" in result.reason
    assert "hour" in result.reason
    assert "lag_cell_1h" in result.reason
    assert "illustrative, not validated" in result.reason
    assert result.details["illustrative"] is True


def test_mock_mode_stays_on_the_grid_and_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tiny_artifact(tmp_path, ["hour", "lag_cell_1h"])
    _point_at_artifact(monkeypatch, tmp_path, mock_mode=True)

    def _osm_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("OSM was called while MOCK_MODE is true")

    monkeypatch.setattr("ml.crime_risk.osm_features.try_osm_features", _osm_called)
    result = crime_risk.signal(_sample())
    assert result.risk == pytest.approx(0.82)
    assert "synthetic crime grid" in result.reason


def test_osm_failure_falls_back_when_the_model_needs_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tiny_artifact(tmp_path, ["hour", "police_distance_m"])
    _point_at_artifact(monkeypatch, tmp_path, mock_mode=False)

    def _osm_failed(*_args: object, **_kwargs: object) -> tuple[None, str]:
        return None, "TimeoutError: blocked"

    monkeypatch.setattr("ml.crime_risk.osm_features.try_osm_features", _osm_failed)
    result = crime_risk.signal(_sample())
    assert result.available is True
    assert result.risk == pytest.approx(0.82)
    missing = _sample().model_copy(update={"location": Location(lat=1.0, lon=1.0)})
    assert crime_risk.signal(missing).available is False
