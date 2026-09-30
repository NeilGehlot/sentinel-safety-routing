"""Train a random forest on 2.5 s windows. The split is by subject.

No random window split. No neural net. No struggle class.
UCI HAR and MobiAct are recorded as skipped. See prepare_data for why.
"""

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from app.config import MOTION_MODEL_META_PATH, MOTION_MODEL_PATH
from ml.motion.evaluate import (
    confusion,
    confusion_lines,
    fall_recall,
    format_metric,
    macro_f1,
    write_report,
)
from ml.motion.prepare_data import (
    FEATURE_NAMES,
    MOBIACT_SKIP,
    UCI_HAR_SKIP,
    WISDM_HZ,
    WISDM_NOTE,
    WINDOW_SECONDS,
    ensure_wisdm,
    load_wisdm,
)

FOREST_PARAMS = {
    "n_estimators": 100,
    "max_depth": 16,
    "min_samples_leaf": 5,
    "class_weight": "balanced",
    "random_state": 0,
    "n_jobs": 1,
}


def held_out_subjects(subjects: list[str]) -> set[str]:
    """Every fifth sorted subject. The same subject is never in both sides."""
    unique = sorted(set(subjects))
    if len(unique) < 2:
        raise RuntimeError("Need at least two subjects for a subject split.")
    chosen = {subject for index, subject in enumerate(unique) if index % 5 == 4}
    if not chosen or chosen == set(unique):
        return {unique[-1]}
    return chosen


def train() -> dict[str, object]:
    """Fit the forest and write the report. Metrics come from the subject holdout."""
    files = ensure_wisdm()
    features, labels, subjects, stats = load_wisdm(files)
    reports = Path(__file__).resolve().parents[1] / "reports"
    report_path = reports / "motion_report.md"
    if features.shape[0] < 2:
        write_report(
            report_path,
            _sections(stats, [], None, None, None, "WISDM produced no windows."),
        )
        raise RuntimeError("WISDM produced no windows.")
    test_ids = held_out_subjects(subjects.tolist())
    test_mask = np.isin(subjects, list(test_ids))
    train_mask = ~test_mask
    if not np.any(train_mask) or not np.any(test_mask):
        write_report(
            report_path,
            _sections(stats, sorted(test_ids), None, None, None, "Subject split was empty."),
        )
        raise RuntimeError("Subject split was empty.")
    forest = RandomForestClassifier(**FOREST_PARAMS)
    forest.fit(features[train_mask], labels[train_mask])
    predicted = forest.predict(features[test_mask])
    class_labels = [str(item) for item in forest.classes_]
    score = macro_f1(labels[test_mask], predicted, class_labels)
    matrix = confusion(labels[test_mask], predicted, class_labels)
    recall = fall_recall(labels[test_mask], predicted)
    model_path = Path(MOTION_MODEL_PATH)
    meta_path = Path(MOTION_MODEL_META_PATH)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(forest, model_path)
    meta = {
        "model": "random_forest",
        "features": list(FEATURE_NAMES),
        "classes": class_labels,
        "window_seconds": WINDOW_SECONDS,
        "sampling_hz": WISDM_HZ,
        "datasets": ["WISDM"],
        "struggle": False,
    }
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    write_report(
        report_path,
        _sections(stats, sorted(test_ids), score, matrix, recall, "", class_labels, predicted.size),
    )
    return {
        "macro_f1": score,
        "fall_recall": recall,
        "classes": class_labels,
        "test_windows": int(predicted.size),
        "train_windows": int(np.count_nonzero(train_mask)),
        "test_subjects": len(test_ids),
        "datasets": ["WISDM"],
        "report": str(report_path),
        "model": str(model_path),
    }


def _sections(
    stats: dict[str, int],
    test_ids: list[str],
    score: float | None,
    matrix: np.ndarray | None,
    recall: float | None,
    error: str,
    class_labels: list[str] | None = None,
    test_windows: int | None = None,
) -> list[tuple[str, list[str]]]:
    labels = class_labels or []
    matrix_lines = ["- Confusion matrix was not computed."]
    if matrix is not None and labels:
        matrix_lines = confusion_lines(labels, matrix)
    fall_line = "- Fall recall was not computed. The test labels do not include fall."
    if recall is not None:
        fall_line = f"- Fall recall: {format_metric(recall)}."
    error_lines = [f"- {error}"] if error else ["- Training completed on the windows below."]
    return [
        (
            "Datasets",
            [
                f"- UCI HAR: {UCI_HAR_SKIP}",
                f"- WISDM: {WISDM_NOTE}",
                f"- MobiAct: {MOBIACT_SKIP}",
                "- Watch and gyroscope streams were not used.",
                "- There is no struggle class.",
            ],
        ),
        (
            "Windows",
            [
                f"- Lines read: {stats.get('rows_read', 0)}. Skipped lines: {stats.get('skipped_lines', 0)}.",
                f"- Kept windows: {stats.get('windows', 0)}. Each window is {WINDOW_SECONDS} s at {WISDM_HZ:g} Hz.",
                "- Mapped codes: A walking, B jogging as running, C stairs as walking, D sitting as stationary, E standing as stationary.",
                "- Vehicle is not a WISDM activity, so the forest has no vehicle class.",
                *error_lines,
            ],
        ),
        (
            "Split",
            [
                "- Subjects are sorted, and every subject whose index modulo 5 is 4 is held out.",
                "- A subject is entirely in train or entirely in test. Windows are not shuffled.",
                f"- Held-out subjects: {len(test_ids)}.",
                f"- Test windows: {test_windows if test_windows is not None else 'not computed'}.",
            ],
        ),
        (
            "Model",
            [
                "- Random forest. Not a neural net.",
                f"- n_estimators {FOREST_PARAMS['n_estimators']}, max_depth {FOREST_PARAMS['max_depth']}, "
                f"min_samples_leaf {FOREST_PARAMS['min_samples_leaf']}, class_weight balanced, random_state 0.",
                "- Features: mean, std, min, max on each axis and on magnitude, dominant frequency, jerk std.",
            ],
        ),
        (
            "Metrics",
            [
                f"- Macro F1: {format_metric(score)}.",
                fall_line,
                "- Confusion matrix:",
                *matrix_lines,
            ],
        ),
    ]


def main() -> None:
    summary = train()
    printable = {key: summary[key] for key in summary if key != "classes"}
    printable["classes"] = summary["classes"]
    printable["fall_recall"] = summary["fall_recall"]
    print(json.dumps(printable))


if __name__ == "__main__":
    main()
