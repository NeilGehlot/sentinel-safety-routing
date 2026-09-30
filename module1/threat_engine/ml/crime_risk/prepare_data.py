"""Build an incident table from LAPD crime rows.

This pipeline is trained on Los Angeles data to demonstrate the method.
Features are city-agnostic and ready for local police data. Gurugram
output is illustrative, not validated. Do not train on NCRB aggregates.
"""

import csv
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx
import numpy as np

LAPD_SODA_CSV = "https://data.lacity.org/resource/2nrs-mtv8.csv"
# Rows outside this box are missing geocodes, not a city identifier in the model.
LAT_MIN = 33.5
LAT_MAX = 34.5
LON_MIN = -119.0
LON_MAX = -117.5
PANEL_START = date(2020, 1, 1)
PANEL_END = date(2024, 12, 31)

DISCLAIMER = (
    "Pipeline trained on LA data to demonstrate the method, "
    "city-agnostic features, ready for local police data. "
    "Gurugram output is illustrative, not validated."
)


@dataclass(frozen=True)
class IncidentTable:
    """Clean incident coordinates and local timestamps. No cell id column."""

    lat: np.ndarray
    lon: np.ndarray
    year: np.ndarray
    month: np.ndarray
    day: np.ndarray
    hour: np.ndarray
    rows_read: int
    rows_kept: int


def parse_hour(value: str) -> int | None:
    """LAPD time_occ is HHMM. Return the hour, or None when it is unusable."""
    text = str(value).strip()
    if not text or not text.isdigit():
        return None
    hour = int(text) // 100
    if hour < 0 or hour > 23:
        return None
    return hour


def bin_index(coord: float, bin_deg: float) -> int:
    """Integer bin. The model never sees this index as a feature."""
    return math.floor(coord / bin_deg)


def panel_hours() -> int:
    """Inclusive hours from the panel start through the panel end."""
    days = (PANEL_END - PANEL_START).days + 1
    return days * 24


def hour_index(year: int, month: int, day: int, hour: int) -> int | None:
    """Hours since PANEL_START. None when the stamp falls outside the panel."""
    try:
        offset = (date(year, month, day) - PANEL_START).days
    except ValueError:
        return None
    if offset < 0:
        return None
    index = offset * 24 + hour
    if index < 0 or index >= panel_hours():
        return None
    return index


def download_lapd(dest: Path, page_size: int = 50000) -> Path:
    """Download lat, lon, and time. Raises if the service does not respond."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    offset = 0
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date_occ", "time_occ", "lat", "lon"])
        writer.writeheader()
        while True:
            response = httpx.get(
                LAPD_SODA_CSV,
                params={
                    "$select": "date_occ,time_occ,lat,lon",
                    "$order": "date_occ,time_occ",
                    "$limit": str(page_size),
                    "$offset": str(offset),
                },
                timeout=120.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            lines = response.text.splitlines()
            reader = csv.DictReader(lines)
            batch = 0
            for row in reader:
                if not row.get("lat") or not row.get("lon") or not row.get("date_occ"):
                    continue
                writer.writerow(
                    {
                        "date_occ": row["date_occ"],
                        "time_occ": row.get("time_occ") or "",
                        "lat": row["lat"],
                        "lon": row["lon"],
                    }
                )
                batch += 1
            if batch < page_size:
                break
            offset += page_size
    return dest


def load_incidents(path: Path) -> IncidentTable:
    """Keep rows with a usable hour and a coordinate inside the LA geocode box."""
    import pandas as pd

    frame = pd.read_csv(path, dtype=str)
    rows_read = int(len(frame))
    lat = pd.to_numeric(frame.get("lat"), errors="coerce")
    lon = pd.to_numeric(frame.get("lon"), errors="coerce")
    hours = frame.get("time_occ", "").map(parse_hour)
    dates = frame.get("date_occ", "").astype(str).str.slice(0, 10)
    parsed = pd.to_datetime(dates, format="%Y-%m-%d", errors="coerce")
    keep = (
        lat.between(LAT_MIN, LAT_MAX)
        & lon.between(LON_MIN, LON_MAX)
        & hours.notna()
        & parsed.notna()
    )
    kept = frame.loc[keep]
    stamp = parsed.loc[keep]
    return IncidentTable(
        lat=lat.loc[keep].to_numpy(dtype=np.float64),
        lon=lon.loc[keep].to_numpy(dtype=np.float64),
        year=stamp.dt.year.to_numpy(dtype=np.int16),
        month=stamp.dt.month.to_numpy(dtype=np.int8),
        day=stamp.dt.day.to_numpy(dtype=np.int8),
        hour=hours.loc[keep].to_numpy(dtype=np.int8),
        rows_read=rows_read,
        rows_kept=int(keep.sum()),
    )


def calendar_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Hour, day of week, month, and year for every hour in the panel."""
    n_hours = panel_hours()
    hour = np.empty(n_hours, dtype=np.int16)
    dow = np.empty(n_hours, dtype=np.int16)
    month = np.empty(n_hours, dtype=np.int16)
    year = np.empty(n_hours, dtype=np.int16)
    start = datetime(PANEL_START.year, PANEL_START.month, PANEL_START.day)
    weekday = start.weekday()
    for index in range(n_hours):
        day_offset = index // 24
        stamp = start.fromordinal(start.toordinal() + day_offset)
        hour[index] = index % 24
        dow[index] = (weekday + day_offset) % 7
        month[index] = stamp.month
        year[index] = stamp.year
    return hour, dow, month, year
