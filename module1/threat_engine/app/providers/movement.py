"""Movement risk from an activity label, a window classifier, or a trivial rule.

The random forest runs only when a window is present, no activity label was
sent, MOCK_MODE is off, and the artifact loads. Otherwise the existing rules
stay. sudden_stop is a speed drop versus the previous request in the same
session. There is no struggle class.
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from app import config
from app.config import (
    ACCEL_FALL_MAGNITUDE_MPS2,
    ACCEL_RUNNING_STDEV_MPS2,
    MOTION_MODEL_META_PATH,
    MOTION_MODEL_PATH,
    MOVEMENT_RISK,
    STATIONARY_SPEED_MPS,
    SUDDEN_STOP_MAX_GAP_SECONDS,
    SUDDEN_STOP_PREV_MIN_SPEED_MPS,
)
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest

_CLASSIFIER_LABELS = {"stationary", "walking", "running", "vehicle", "fall"}
_MODEL_CACHE: dict[str, "_LoadedMotion"] = {}


@dataclass
class _LoadedMotion:
    model: object
    classes: set[str]


def _magnitude(sample: list[float]) -> float | None:
    if len(sample) < 3:
        return None
    try:
        x_axis, y_axis, z_axis = float(sample[0]), float(sample[1]), float(sample[2])
    except (TypeError, ValueError):
        return None
    return math.sqrt(x_axis * x_axis + y_axis * y_axis + z_axis * z_axis)


def label_from_window(window: list[list[float]]) -> str | None:
    """Trivial window rule: a large peak is a fall, high spread is running, else stationary."""
    magnitudes = [item for item in (_magnitude(sample) for sample in window) if item is not None]
    if not magnitudes:
        return None
    if max(magnitudes) >= ACCEL_FALL_MAGNITUDE_MPS2:
        return "fall"
    mean = sum(magnitudes) / len(magnitudes)
    variance = sum((item - mean) ** 2 for item in magnitudes) / len(magnitudes)
    if math.sqrt(variance) >= ACCEL_RUNNING_STDEV_MPS2:
        return "running"
    return "stationary"


def reset_model_cache() -> None:
    """Drop a loaded forest so tests can swap the artifact path."""
    _MODEL_CACHE.clear()


def _load_model() -> _LoadedMotion | None:
    model_path = Path(MOTION_MODEL_PATH)
    meta_path = Path(MOTION_MODEL_META_PATH)
    if not model_path.is_file() or not meta_path.is_file():
        return None
    key = f"{model_path.resolve()}|{model_path.stat().st_mtime_ns}|{meta_path.stat().st_mtime_ns}"
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    import joblib

    from ml.motion.prepare_data import FEATURE_NAMES

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    features = meta.get("features")
    classes = meta.get("classes")
    if list(features or []) != list(FEATURE_NAMES):
        return None
    if not isinstance(classes, list) or not classes:
        return None
    model = joblib.load(model_path)
    loaded = _LoadedMotion(model=model, classes={str(item) for item in classes})
    _MODEL_CACHE.clear()
    _MODEL_CACHE[key] = loaded
    return loaded


def _from_model(window: list[list[float]], sampling_hz: float | None) -> str | None:
    """Classifier label, or None so the caller keeps the rule."""
    try:
        loaded = _load_model()
        if loaded is None:
            return None
        from ml.motion.prepare_data import FEATURE_NAMES, window_features

        vector = window_features(window, sampling_hz)
        if vector is None or vector.shape != (len(FEATURE_NAMES),) or not np.isfinite(vector).all():
            return None
        label = str(loaded.model.predict(vector.reshape(1, -1))[0])
        if label not in _CLASSIFIER_LABELS or label not in loaded.classes:
            return None
        return label
    except Exception:
        return None


def sudden_stop(
    speed_mps: float | None,
    moment: datetime | None,
    previous_speed: float | None,
    previous_at: datetime | None,
) -> bool:
    """True when speed falls from a moving pace to a stop inside the configured gap."""
    if speed_mps is None or previous_speed is None or moment is None or previous_at is None:
        return False
    elapsed = (moment - previous_at).total_seconds()
    if elapsed < 0 or elapsed > SUDDEN_STOP_MAX_GAP_SECONDS:
        return False
    return previous_speed >= SUDDEN_STOP_PREV_MIN_SPEED_MPS and speed_mps <= STATIONARY_SPEED_MPS


def _choose(labels: list[str]) -> str | None:
    known = [label for label in labels if label in MOVEMENT_RISK]
    if not known:
        return None
    return max(known, key=lambda label: MOVEMENT_RISK[label])


def signal(
    request: AssessRequest,
    previous_speed: float | None = None,
    previous_at: datetime | None = None,
) -> SignalResult:
    """Use an activity label, else the forest when it loads, else the window rule."""
    try:
        movement = request.movement
        labels: list[str] = []
        used_model = False
        if movement is not None and movement.activity is not None:
            labels.append(movement.activity.value)
        elif movement is not None and movement.accel_window:
            from_model = None
            if not config.MOCK_MODE:
                from_model = _from_model(movement.accel_window, movement.sampling_hz)
            if from_model is not None:
                labels.append(from_model)
                used_model = True
            else:
                from_window = label_from_window(movement.accel_window)
                if from_window is not None:
                    labels.append(from_window)
        speed = request.location.speed_mps if request.location is not None else None
        if sudden_stop(speed, request.timestamp, previous_speed, previous_at):
            labels.append("sudden_stop")
        label = _choose(labels)
        if label is None:
            return unavailable("movement", "Movement is missing.")
        risk = clamp_risk(MOVEMENT_RISK[label])
        if label == "sudden_stop":
            reason = "speed dropped suddenly"
        elif used_model:
            reason = f"movement classifier labels this window as {label.replace('_', ' ')}"
        else:
            reason = f"movement is {label.replace('_', ' ')}"
        return SignalResult(
            name="movement",
            risk=risk,
            reason=reason,
            available=True,
            details={"activity": label},
        )
    except Exception:
        return unavailable("movement", "Movement could not be read.")
