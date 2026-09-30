# Crime risk model evaluation

Pipeline trained on LA data to demonstrate the method, city-agnostic features, ready for local police data. Gurugram output is illustrative, not validated.

## Data

- Source: LAPD Crime Data from 2020 to Present (Socrata 2nrs-mtv8). Not NCRB.
- Rows read: 1004894. Rows kept after geocode and hour checks: 1002654.
- Grid: 0.05 degrees. Cells with at least 50 incidents: 77.
- Panel rows: 3376296. Positive hours in the training slice: 467113.
- OSM features used: False.
- OSM note: HTTPStatusError: Server error '504 Gateway Timeout' for url 'https://overpass-api.de/api/interpreter'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/504

## Split

- Temporal train: years before 2024, excluding the northern spatial holdout.
- Temporal test: 2024 in the same cells. No random split.
- Spatial holdout: cells at or above lat-bin quantile 0.8 (20 cells). Those cells are absent from training.

## Metrics

- Temporal test prevalence (share of cell-hours with an incident): 0.151206.
- Model PR-AUC on the temporal test: 0.451519.
- Baseline PR-AUC (training-period average for that cell and hour): 0.466661.
- The model does not beat the baseline. Model PR-AUC is 0.451519 and the cell-hour historical average PR-AUC is 0.466661.
- Spatial holdout PR-AUC on years before 2024: 0.319664.
- Spatial holdout PR-AUC in 2024: 0.253039.
- The cell-hour baseline is only scored on the temporal test, where those cells were seen in earlier years.

## Calibration

- Quantile calibration curve: crime_risk_calibration.svg.
- Pipeline trained on LA data to demonstrate the method, city-agnostic features, ready for local police data. Gurugram output is illustrative, not validated.
