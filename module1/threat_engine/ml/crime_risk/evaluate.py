"""Score a temporal split and a spatial holdout. No random split.

Metrics are computed from the arrays passed in. This module does not invent them.
"""

from pathlib import Path

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import average_precision_score

from ml.crime_risk.prepare_data import DISCLAIMER


def pr_auc(y_true: np.ndarray, proba: np.ndarray) -> float:
    """Average precision. Raises if the arrays are empty or one class is missing."""
    return float(average_precision_score(y_true, proba))


def cell_hour_rates(
    y_values: np.ndarray,
    cell_index: np.ndarray,
    hour_of_day: np.ndarray,
    n_cells: int,
) -> np.ndarray:
    """Positive rate for each cell and hour of day, from the rows that are passed in."""
    sums = np.zeros((n_cells, 24), dtype=np.float64)
    counts = np.zeros((n_cells, 24), dtype=np.float64)
    np.add.at(sums, (cell_index, hour_of_day), y_values)
    np.add.at(counts, (cell_index, hour_of_day), 1.0)
    return np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)


def calibration_points(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Fraction of positives and mean predicted probability in each quantile bin."""
    observed, predicted = calibration_curve(y_true, proba, n_bins=n_bins, strategy="quantile")
    return np.asarray(predicted, dtype=np.float64), np.asarray(observed, dtype=np.float64)


def write_calibration_svg(path: Path, predicted: np.ndarray, observed: np.ndarray) -> None:
    """Write a calibration curve as SVG. No extra plotting dependency."""
    width = 480
    height = 480
    pad = 48

    def _x(value: float) -> float:
        return pad + (width - 2 * pad) * float(value)

    def _y(value: float) -> float:
        return height - pad - (height - 2 * pad) * float(value)

    points = " ".join(f"{_x(x_value):.2f},{_y(y_value):.2f}" for x_value, y_value in zip(predicted, observed))
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{pad}" stroke="#bbbbbb" stroke-dasharray="4 4"/>
  <polyline fill="none" stroke="#1f4e79" stroke-width="2" points="{points}"/>
  <text x="{width / 2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="16">Calibration curve</text>
  <text x="{width / 2}" y="{height - 12}" text-anchor="middle" font-family="sans-serif" font-size="12">Mean predicted probability</text>
  <text x="16" y="{height / 2}" transform="rotate(-90 16 {height / 2})" text-anchor="middle" font-family="sans-serif" font-size="12">Fraction of hours with an incident</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def write_report(path: Path, sections: list[tuple[str, list[str]]]) -> None:
    """Write the evaluation report from already computed lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [f"# Crime risk model evaluation\n\n{DISCLAIMER}\n"]
    for title, lines in sections:
        chunks.append(f"\n## {title}\n")
        chunks.extend(f"\n{line}" for line in lines)
        chunks.append("\n")
    path.write_text("".join(chunks), encoding="utf-8")


def format_metric(value: float | None) -> str:
    if value is None:
        return "not computed"
    return f"{value:.6f}"


def comparison_line(model_auc: float, baseline_auc: float) -> str:
    if model_auc > baseline_auc:
        return (
            f"The model PR-AUC ({model_auc:.6f}) is higher than the cell-hour baseline "
            f"({baseline_auc:.6f})."
        )
    return (
        f"The model does not beat the baseline. Model PR-AUC is {model_auc:.6f} and the "
        f"cell-hour historical average PR-AUC is {baseline_auc:.6f}."
    )

