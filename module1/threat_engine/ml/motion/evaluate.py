"""Subject-split scores for the movement classifier. No random window split.

Metrics are computed from the arrays passed in. This module does not invent them.
"""

from pathlib import Path

import numpy as np
from sklearn.metrics import confusion_matrix, f1_score


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, labels: list[str]) -> float:
    """Macro F1 over the labels that were trained. Missing labels contribute 0."""
    return float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))


def confusion(y_true: np.ndarray, y_pred: np.ndarray, labels: list[str]) -> np.ndarray:
    """Rows are true labels. Columns are predicted labels. Order follows labels."""
    return confusion_matrix(y_true, y_pred, labels=labels)


def fall_recall(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    """Recall of the fall class. None when the test set has no fall labels."""
    true = np.asarray(y_true)
    mask = true == "fall"
    if not np.any(mask):
        return None
    predicted = np.asarray(y_pred)
    return float(np.mean(predicted[mask] == "fall"))


def format_metric(value: float | None) -> str:
    if value is None:
        return "not computed"
    return f"{value:.6f}"


def confusion_lines(labels: list[str], matrix: np.ndarray) -> list[str]:
    header = "| true \\ predicted | " + " | ".join(labels) + " |"
    separator = "| --- | " + " | ".join("---" for _ in labels) + " |"
    lines = [header, separator]
    for label, row in zip(labels, matrix):
        cells = " | ".join(str(int(value)) for value in row)
        lines.append(f"| {label} | {cells} |")
    return lines


def write_report(path: Path, sections: list[tuple[str, list[str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = ["# Movement classifier evaluation\n"]
    for title, lines in sections:
        chunks.append(f"\n## {title}\n")
        chunks.extend(f"\n{line}" for line in lines)
        chunks.append("\n")
    path.write_text("".join(chunks), encoding="utf-8")
