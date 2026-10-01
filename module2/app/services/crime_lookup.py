"""Map lat/lng to precomputed district/city historical-crime safety scores."""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA = Path(__file__).resolve().parents[2] / "data"
NATIONAL_MEAN_SAFETY = 46.4  # 100 - 53.6 published mean risk
CITY_RADIUS_M = 35_000
DISTRICT_RADIUS_M = 95_000
SPECIAL_UNIT = re.compile(
    r"cid|railway|railways|\bgrp\b|\bats\b|\bstf\b|vigilance|spl\s*cell|"
    r"crime branch|traffic|eou|cyber cell",
    re.I,
)
_STRIP = re.compile(r"[^a-z0-9]+")


def _norm(name: str) -> str:
    s = (name or "").lower()
    for token in ("commr", "commissionerate", "city", "rural", "dist"):
        s = s.replace(token, " ")
    return _STRIP.sub("", s)


def haversine_m(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    dp = p2 - p1
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(h, 1.0)))


def is_special_unit(name: str) -> bool:
    return bool(SPECIAL_UNIT.search(name or ""))


def _load_json(name: str):
    path = DATA / name
    if not path.exists():
        return []
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _tables():
    districts = [
        r for r in _load_json("district-safety-scores.json")
        if not is_special_unit(r.get("district") or "")
    ]
    cities = _load_json("city-safety-scores.json")
    gazetteer = [
        g for g in _load_json("gazetteer.json")
        if not is_special_unit(g.get("name") or "")
    ]
    d_by_key = {(_norm(r["state_ut"] or ""), _norm(r["district"])): r for r in districts}
    d_by_name = {}
    for r in districts:
        d_by_name.setdefault(_norm(r["district"]), r)
    c_by_name = {_norm(r["city"]): r for r in cities}
    return {
        "districts": districts,
        "cities": cities,
        "gazetteer": gazetteer,
        "d_by_key": d_by_key,
        "d_by_name": d_by_name,
        "c_by_name": c_by_name,
    }


def _fallback(reason: str) -> dict:
    return {
        "safety_score": NATIONAL_MEAN_SAFETY,
        "source": "national_mean",
        "reason": reason,
        "district": None,
        "city": None,
        "state_ut": None,
        "matched": False,
    }


def _score_from_place(place: dict) -> Optional[dict]:
    tables = _tables()
    if place["kind"] == "city":
        row = tables["c_by_name"].get(_norm(place["name"]))
        if not row:
            return None
        return {
            "safety_score": float(row["safety_score"]),
            "source": "city",
            "reason": "nearest_city",
            "district": row.get("matched_district"),
            "city": row["city"],
            "state_ut": row.get("state_ut") or place.get("state_ut"),
            "matched": True,
        }
    key = (_norm(place.get("state_ut") or ""), _norm(place["name"]))
    row = tables["d_by_key"].get(key) or tables["d_by_name"].get(_norm(place["name"]))
    if not row:
        return None
    return {
        "safety_score": float(row["safety_score"]),
        "source": "district",
        "reason": "nearest_district",
        "district": row["district"],
        "city": None,
        "state_ut": row.get("state_ut"),
        "matched": True,
    }


def historical_crime_for(lat: float, lng: float) -> dict:
    """Resolve a map point to a crime-only safety_score. Never 0 or 100."""
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return _fallback("invalid_coords")
    if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
        return _fallback("invalid_coords")

    tables = _tables()
    if not tables["gazetteer"] or (not tables["cities"] and not tables["districts"]):
        return _fallback("lookup_missing")

    pt = (lat_f, lng_f)
    best_city = best_dist = None
    city_d = district_d = None
    for place in tables["gazetteer"]:
        d = haversine_m(pt, (place["lat"], place["lng"]))
        if place["kind"] == "city":
            if city_d is None or d < city_d:
                city_d, best_city = d, place
        else:
            if district_d is None or d < district_d:
                district_d, best_dist = d, place

    hit = None
    if best_city is not None and city_d is not None and city_d <= CITY_RADIUS_M:
        hit = _score_from_place(best_city)
    if hit is None and best_dist is not None and district_d is not None and district_d <= DISTRICT_RADIUS_M:
        hit = _score_from_place(best_dist)
    if hit is None:
        return _fallback("unknown_location")

    score = min(89.5, max(10.5, float(hit["safety_score"])))
    if score in (0.0, 100.0):
        score = NATIONAL_MEAN_SAFETY
    hit["safety_score"] = round(score, 1)
    hit["place_key"] = f"{hit.get('state_ut')}|{hit.get('city') or hit.get('district')}"
    return hit
