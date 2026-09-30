"""Movement classifier fallback. MOCK_MODE stays on the accelerometer rule."""

import json
from pathlib import Path

import numpy as np
import pytest

from app import config
from app.providers import movement
from app.schemas import AssessRequest, Location, Movement
from ml.motion.prepare_data import FEATURE_NAMES, window_features
from ml.motion.train import held_out_subjects

SAMPLE = AssessRequest.model_validate(
    {
        "session_id": "abc",
        "timestamp": "2026-09-29T23:40:00+05:30",
        "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
        "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
    }
)


def _point_at(monkeypatch: pytest.MonkeyPatch, directory: Path, mock_mode: bool) -> None:
    monkeypatch.setattr(config, "MOCK_MODE", mock_mode)
    monkeypatch.setattr(movement, "MOTION_MODEL_PATH", str(directory / "motion.joblib"))
    monkeypatch.setattr(movement, "MOTION_MODEL_META_PATH", str(directory / "motion_meta.json"))
    movement.reset_model_cache()


def _tiny_forest(directory: Path) -> None:
    import joblib
    from sklearn.ensemble import RandomForestClassifier

    rows = np.zeros((12, len(FEATURE_NAMES)), dtype=np.float64)
    rows[6:, 0] = 5.0
    labels = np.array(["stationary"] * 6 + ["walking"] * 6)
    forest = RandomForestClassifier(n_estimators=5, random_state=0, n_jobs=1)
    forest.fit(rows, labels)
    joblib.dump(forest, directory / "motion.joblib")
    meta = {"features": list(FEATURE_NAMES), "classes": ["stationary", "walking"]}
    (directory / "motion_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_missing_artifact_falls_back_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MOCK_MODE", False)
    monkeypatch.setattr(movement, "MOTION_MODEL_PATH", "/tmp/motion-missing.joblib")
    monkeypatch.setattr(movement, "MOTION_MODEL_META_PATH", "/tmp/motion-missing.json")
    movement.reset_model_cache()
    result = movement.signal(SAMPLE)
    assert result.available is True
    assert result.details["activity"] == "stationary"
    assert 0.0 <= result.risk <= 1.0


def test_broken_artifact_falls_back_without_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "motion.joblib").write_text("not a forest", encoding="utf-8")
    (tmp_path / "motion_meta.json").write_text("{", encoding="utf-8")
    _point_at(monkeypatch, tmp_path, mock_mode=False)
    result = movement.signal(SAMPLE)
    assert result.available is True
    assert result.details["activity"] == "stationary"


def test_classifier_output_stays_in_allowed_activities(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tiny_forest(tmp_path)
    _point_at(monkeypatch, tmp_path, mock_mode=False)
    result = movement.signal(SAMPLE)
    assert result.details["activity"] in {"stationary", "walking", "running", "vehicle", "fall"}
    assert 0.0 <= result.risk <= 1.0
    assert "classifier" in result.reason
    labeled = SAMPLE.model_copy(update={"movement": Movement(activity="running")})
    assert movement.signal(labeled).details["activity"] == "running"


def test_window_features_are_finite() -> None:
    window = [[0.1 * index, 9.8, 0.2] for index in range(50)]
    values = window_features(window, 50.0)
    assert values is not None
    assert values.shape == (len(FEATURE_NAMES),)
    assert np.isfinite(values).all()
    dirty = [[float("nan"), 1.0, 1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
    cleaned = window_features(dirty, 20.0)
    assert cleaned is not None
    assert np.isfinite(cleaned).all()
    assert window_features([[float("nan"), float("nan"), float("nan")]], 50.0) is None


def test_mock_mode_stays_on_the_rule(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _tiny_forest(tmp_path)
    _point_at(monkeypatch, tmp_path, mock_mode=True)

    def _offline(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the motion artifact was loaded while MOCK_MODE is true")

    monkeypatch.setattr(movement, "_load_model", _offline)
    result = movement.signal(SAMPLE)
    assert result.details["activity"] == "stationary"
    assert "classifier" not in result.reason


def test_sudden_stop_still_comes_from_speed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tiny_forest(tmp_path)
    _point_at(monkeypatch, tmp_path, mock_mode=False)
    stopped = movement.signal(
        SAMPLE.model_copy(update={"location": Location(lat=28.45, lon=77.02, speed_mps=0.0)}),
        previous_speed=2.0,
        previous_at=SAMPLE.timestamp,
    )
    assert stopped.details["activity"] == "sudden_stop"


def test_subject_split_keeps_each_subject_on_one_side() -> None:
    subjects = [f"wisdm:{1600 + index // 3}" for index in range(30)]
    first = held_out_subjects(subjects)
    second = held_out_subjects(list(reversed(subjects)))
    assert first == second
    assert first.isdisjoint(set(subjects) - first)
    assert first
    assert set(subjects) - first
