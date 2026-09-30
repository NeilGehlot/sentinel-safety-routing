import hashlib

from app.services import risk_engine
from app.services.geo import haversine

FOLLOWER = {
    "min_locations": 3,
    "min_separation_m": 150,
    "min_duration_s": 20 * 60,
    "min_rssi": -70,
    "crowd_devices": 15,
    "crowd_radius_m": 100,
    "alert_delta": 30,
}


def buildFingerprint(adv):
    # MAC is never part of the fingerprint; it rotates.
    ad = ",".join(f"{t}:{len(v)}" for t, v in adv.get("ad_structures", []))
    raw = f"{adv.get('name') or ''}|{adv.get('manufacturer_id')}|{adv.get('tx_power')}|{ad}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _crowded(fp, events, c):
    # "addr" is only used to count distinct radios near each sighting, never as a key.
    for e in events:
        if e["fingerprint"] != fp:
            continue
        near = {x.get("addr") for x in events if x["fingerprint"] == fp
                and haversine((e["lat"], e["lng"]), (x["lat"], x["lng"])) <= c["crowd_radius_m"]}
        if len(near) >= c["crowd_devices"]:
            return True
    return False


def detectFollower(events, paired=(), c=FOLLOWER):
    best = {"flagged": False, "fingerprint": None, "sightings": 0, "distanceSpanM": 0.0}
    for fp in {e["fingerprint"] for e in events} - set(paired):
        s = sorted((e for e in events if e["fingerprint"] == fp), key=lambda e: e["timestamp"])
        if not s or any(e["rssi"] < c["min_rssi"] for e in s) or _crowded(fp, events, c):
            continue
        locs = []
        for e in s:
            p = (e["lat"], e["lng"])
            if all(haversine(p, q) >= c["min_separation_m"] for q in locs):
                locs.append(p)
        span = max((haversine(a, b) for a in locs for b in locs), default=0.0)
        flagged = (len(locs) >= c["min_locations"]
                   and s[-1]["timestamp"] - s[0]["timestamp"] >= c["min_duration_s"])
        if flagged or len(s) > best["sightings"]:
            best = {"flagged": flagged, "fingerprint": fp, "sightings": len(s), "distanceSpanM": span}
        if flagged:
            break
    return best


def report(emergency, result):
    if result["flagged"]:
        return risk_engine.update_risk(emergency, "FOLLOWER_DETECTED",
                                       "Possible BLE follower detected", FOLLOWER["alert_delta"])
    return None
