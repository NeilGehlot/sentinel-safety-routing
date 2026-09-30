from app.services.follower_detector import buildFingerprint, detectFollower, report

ADV = {"name": "Tag", "manufacturer_id": 76, "tx_power": -8, "ad_structures": [(1, b"\x06"), (255, b"\x4c\x00\x12")]}


def test_follower_flagged_across_mac_change_and_static_not_flagged():
    fp = buildFingerprint(ADV)
    pts = [(12.9716, 77.5946), (12.9736, 77.5946), (12.9756, 77.5946), (12.9776, 77.5946)]
    moving = [{"fingerprint": fp, "timestamp": i * 600, "lat": la, "lng": ln, "rssi": -55,
               "addr": "AA:01" if i < 2 else "BB:02"} for i, (la, ln) in enumerate(pts)]
    r = detectFollower(moving)
    assert r["flagged"] and r["fingerprint"] == fp and r["sightings"] == 4 and r["distanceSpanM"] > 600
    emergency = {"risk_score": 0}
    assert "Possible BLE follower detected" in report(emergency, r)["trigger_reasons"]

    static = [{"fingerprint": fp, "timestamp": i * 600, "lat": 12.9716, "lng": 77.5946, "rssi": -55}
              for i in range(4)]
    assert not detectFollower(static)["flagged"]
