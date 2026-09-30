"""Adjacent chip steps must move the score by at least 3."""

from datetime import datetime, timedelta, timezone

from app.engine import collect_signals, reset_session_memory
from app.scoring import score_signals
from app.schemas import AssessRequest

IST = timezone(timedelta(hours=5, minutes=30))
_SIGNALS = (
    ("No signal -125", -125),
    ("Weak -108", -108),
    ("Okay -95", -95),
    ("Strong -75", -75),
)
_PEOPLE = (
    ("Nobody 0,0", 0, 0),
    ("A few 5,3", 5, 3),
    ("Some 15,8", 15, 8),
    ("Crowded 40,20", 40, 20),
)


def _score(dbm: int, wifi: int, ble: int, battery: int = 80) -> int:
    body = {
        "timestamp": datetime(2026, 9, 29, 14, 0, tzinfo=IST).isoformat(),
        "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4},
        "device": {"cellular_dbm": dbm, "internet_available": True, "battery_pct": battery},
        "movement": {"activity": "walking"},
        "nearby_devices": {"wifi_count": wifi, "ble_count": ble},
    }
    reset_session_memory()
    signals = collect_signals(AssessRequest.model_validate(body), None)
    return score_signals(signals).score


def _rows() -> list[tuple[str, int, int | None]]:
    rows: list[tuple[str, int, int | None]] = []
    previous: int | None = None
    for label, dbm in _SIGNALS:
        score = _score(dbm, 5, 3)
        delta = None if previous is None else score - previous
        rows.append((label, score, delta))
        previous = score
    previous = None
    for label, wifi, ble in _PEOPLE:
        score = _score(-95, wifi, ble)
        delta = None if previous is None else score - previous
        rows.append((label, score, delta))
        previous = score
    return rows


def test_adjacent_signal_and_people_steps_change_the_score() -> None:
    rows = _rows()
    print(f"{'input':22} {'score':>5} {'delta':>6}")
    for label, score, delta in rows:
        shown = "" if delta is None else f"{delta:+d}"
        print(f"{label:22} {score:5} {shown:>6}")
    for _label, score, delta in rows:
        if delta is not None:
            assert abs(delta) >= 3
    full = _score(-95, 5, 3, 100)
    drained = _score(-95, 5, 3, 0)
    slightly = _score(-95, 5, 3, 90)
    print(f"{'Battery 100':22} {full:5}")
    print(f"{'Battery 90':22} {slightly:5} {slightly - full:+6d}")
    print(f"{'Battery 0':22} {drained:5} {drained - full:+6d}")
    assert abs(drained - full) >= 9
    assert abs(slightly - full) >= 1
