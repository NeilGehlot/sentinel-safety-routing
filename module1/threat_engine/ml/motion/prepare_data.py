"""Build 2.5 s accelerometer windows for the movement classifier.

UCI HAR is not loaded. Its dataset notice says commercial use is prohibited.
MobiAct is not loaded. It requires a signed research agreement.
WISDM phone accelerometer data is CC BY 4.0 and is sampled at 20 Hz.
"""

import os
import zipfile
from pathlib import Path

import numpy as np

WINDOW_SECONDS = 2.5
WISDM_HZ = 20.0
FEATURE_NAMES = (
    "x_mean",
    "x_std",
    "x_min",
    "x_max",
    "y_mean",
    "y_std",
    "y_min",
    "y_max",
    "z_mean",
    "z_std",
    "z_min",
    "z_max",
    "mag_mean",
    "mag_std",
    "mag_min",
    "mag_max",
    "dominant_frequency_hz",
    "jerk_std",
)
CLASSIFIER_LABELS = ("stationary", "walking", "running", "vehicle", "fall")

# Phone accelerometer codes from the WISDM dataset description. Other codes
# (typing, eating, kicking, and the rest) are not these five activities.
WISDM_LABELS = {
    "A": "walking",
    "B": "running",
    "C": "walking",
    "D": "stationary",
    "E": "stationary",
}

UCI_HAR_SKIP = (
    "Skipped. UCI HAR Dataset.names says: 'Any commercial use is prohibited.' "
    "The UCI catalog page also displays CC BY 4.0. This module follows the "
    "dataset notice and does not train on it. The UCI page lists a 50 Hz "
    "sampling rate and published windows of 2.56 s (128 samples)."
)
WISDM_NOTE = (
    "Used. UCI catalog license: Creative Commons Attribution 4.0 International "
    "(CC BY 4.0), which allows use with attribution. Weiss, G. (2019). WISDM "
    "Smartphone and Smartwatch Activity and Biometrics Dataset. UCI Machine "
    "Learning Repository. https://doi.org/10.24432/C5HK59. Phone accelerometer "
    "only, sampled at 20 Hz. Windows are 2.5 s (50 samples). No vehicle activity "
    "and no fall activity are in this dataset."
)
MOBIACT_SKIP = (
    "Skipped. The Biomedical Informatics and eHealth Laboratory says MobiAct "
    "is available on request for non-commercial research and education only, "
    "after a database usage agreement is signed "
    "(https://bmi.hmu.gr/the-mobifall-and-mobiact-datasets-2/). No agreement "
    "is in place, so the files were not downloaded. Capture uses "
    "SENSOR_DELAY_FASTEST, which is not one published sampling rate."
)

WISDM_PAGE = (
    "https://archive.ics.uci.edu/static/public/507/"
    "wisdm+smartphone+and+smartwatch+activity+and+biometrics+dataset.zip"
)
_GAP_NS = int(3 * (1_000_000_000 / WISDM_HZ))


def window_features(window: object, sampling_hz: float | None) -> np.ndarray | None:
    """Mean, std, min, max, magnitude, dominant frequency, and jerk. Finite or None."""
    rows: list[list[float]] = []
    if not isinstance(window, (list, tuple, np.ndarray)):
        return None
    for sample in window:
        if isinstance(sample, np.ndarray):
            values = sample.tolist()
        elif isinstance(sample, (list, tuple)):
            values = list(sample)
        else:
            continue
        if len(values) < 3:
            continue
        try:
            point = [float(values[0]), float(values[1]), float(values[2])]
        except (TypeError, ValueError):
            continue
        if not all(np.isfinite(item) for item in point):
            continue
        rows.append(point)
    if not rows:
        return None
    axes = np.asarray(rows, dtype=np.float64)
    magnitude = np.sqrt(np.sum(axes * axes, axis=1))
    pieces = []
    for column in range(3):
        series = axes[:, column]
        pieces.extend(_span(series))
    pieces.extend(_span(magnitude))
    pieces.append(_dominant_frequency(magnitude, sampling_hz))
    pieces.append(_jerk_std(magnitude, sampling_hz))
    features = np.asarray(pieces, dtype=np.float64)
    features[~np.isfinite(features)] = 0.0
    return features


def _span(series: np.ndarray) -> list[float]:
    return [
        float(np.mean(series)),
        float(np.std(series)),
        float(np.min(series)),
        float(np.max(series)),
    ]


def _dominant_frequency(magnitude: np.ndarray, sampling_hz: float | None) -> float:
    count = int(magnitude.size)
    if sampling_hz is None or sampling_hz <= 0 or count < 4:
        return 0.0
    centered = magnitude - float(np.mean(magnitude))
    power = np.abs(np.fft.rfft(centered)) ** 2
    if power.size < 2:
        return 0.0
    power[0] = 0.0
    if not np.isfinite(power).all():
        return 0.0
    bin_index = int(np.argmax(power))
    freqs = np.fft.rfftfreq(count, d=1.0 / float(sampling_hz))
    return float(freqs[bin_index])


def _jerk_std(magnitude: np.ndarray, sampling_hz: float | None) -> float:
    if sampling_hz is None or sampling_hz <= 0 or magnitude.size < 2:
        return 0.0
    jerk = np.diff(magnitude) * float(sampling_hz)
    if not np.isfinite(jerk).all():
        return 0.0
    return float(np.std(jerk))


def data_root() -> Path:
    return Path(os.getenv("MOTION_DATA_DIR", "/tmp/motion"))


def accel_files(root: Path | None = None) -> list[Path]:
    base = data_root() if root is None else root
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("data_*_accel_phone.txt") if path.is_file())


def ensure_wisdm(root: Path | None = None) -> list[Path]:
    """Return phone-accel files, downloading the CC BY 4.0 archive when needed."""
    base = data_root() if root is None else root
    found = accel_files(base)
    if found:
        return found
    base.mkdir(parents=True, exist_ok=True)
    outer = base / "wisdm.zip"
    inner = base / "wisdm-dataset.zip"
    if not inner.is_file():
        if not outer.is_file():
            _download(WISDM_PAGE, outer)
        _extract_named(outer, "wisdm-dataset.zip", inner)
    dest = base / "wisdm-phone-accel"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(inner) as archive:
        for info in archive.infolist():
            if not info.filename.endswith("_accel_phone.txt"):
                continue
            target = dest / Path(info.filename).name
            with archive.open(info) as source, target.open("wb") as handle:
                handle.write(source.read())
    return accel_files(base)


def _download(url: str, dest: Path) -> None:
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(600.0)
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def _extract_named(archive_path: Path, member: str, dest: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        with archive.open(member) as source, dest.open("wb") as handle:
            handle.write(source.read())


def load_wisdm(files: list[Path]) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, int]]:
    """Non-overlapping 2.5 s windows. Subject ids stay attached to every window."""
    width = int(round(WINDOW_SECONDS * WISDM_HZ))
    features: list[np.ndarray] = []
    labels: list[str] = []
    subjects: list[str] = []
    rows_read = 0
    skipped = 0
    for path in files:
        rows_read, skipped = _consume_file(path, width, features, labels, subjects, rows_read, skipped)
    if not features:
        empty = np.empty((0, len(FEATURE_NAMES)), dtype=np.float64)
        return empty, np.empty(0, dtype=object), np.empty(0, dtype=object), {
            "rows_read": rows_read,
            "windows": 0,
            "skipped_lines": skipped,
        }
    matrix = np.vstack(features)
    stats = {"rows_read": rows_read, "windows": int(matrix.shape[0]), "skipped_lines": skipped}
    return matrix, np.asarray(labels, dtype=object), np.asarray(subjects, dtype=object), stats


def _consume_file(
    path: Path,
    width: int,
    features: list[np.ndarray],
    labels: list[str],
    subjects: list[str],
    rows_read: int,
    skipped: int,
) -> tuple[int, int]:
    subject = ""
    code = ""
    stamp = 0
    samples: list[list[float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            rows_read += 1
            parsed = _parse_wisdm_line(line)
            if parsed is None:
                skipped += 1
                continue
            next_subject, next_code, next_stamp, point = parsed
            label = WISDM_LABELS.get(next_code)
            if label is None:
                skipped += 1
                _flush(samples, subject, code, width, features, labels, subjects)
                samples = []
                subject = ""
                code = ""
                continue
            gap = subject != "" and (
                next_subject != subject or next_code != code or next_stamp - stamp <= 0 or next_stamp - stamp > _GAP_NS
            )
            if gap:
                _flush(samples, subject, code, width, features, labels, subjects)
                samples = []
            subject = next_subject
            code = next_code
            stamp = next_stamp
            samples.append(point)
    _flush(samples, subject, code, width, features, labels, subjects)
    return rows_read, skipped


def _parse_wisdm_line(line: str) -> tuple[str, str, int, list[float]] | None:
    text = line.strip()
    if text.endswith(";"):
        text = text[:-1]
    parts = text.split(",")
    if len(parts) < 6:
        return None
    try:
        point = [float(parts[3]), float(parts[4]), float(parts[5])]
        stamp = int(float(parts[2]))
    except ValueError:
        return None
    if not parts[0] or not parts[1] or not all(np.isfinite(point)):
        return None
    return parts[0], parts[1], stamp, point


def _flush(
    samples: list[list[float]],
    subject: str,
    code: str,
    width: int,
    features: list[np.ndarray],
    labels: list[str],
    subjects: list[str],
) -> None:
    label = WISDM_LABELS.get(code)
    if label is None or not subject or len(samples) < width:
        return
    subject_id = f"wisdm:{subject}"
    usable = len(samples) - (len(samples) % width)
    block = np.asarray(samples[:usable], dtype=np.float64).reshape(-1, width, 3)
    for window in block:
        vector = window_features(window, WISDM_HZ)
        if vector is None or vector.shape != (len(FEATURE_NAMES),):
            continue
        features.append(vector)
        labels.append(label)
        subjects.append(subject_id)
