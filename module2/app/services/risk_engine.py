from app.services import store


def level_for_score(score):
    if score <= 29:
        return "LOW"
    if score <= 59:
        return "SUSPICIOUS"
    if score <= 79:
        return "HIGH"
    return "CRITICAL"


def compute_risk(emergency_or_journey_id):
    emergency = None
    if isinstance(emergency_or_journey_id, dict):
        emergency = emergency_or_journey_id
    elif isinstance(emergency_or_journey_id, str):
        emergency = store.emergencies.get(emergency_or_journey_id)
        if emergency is None:
            journey = store.sos_journeys.get(emergency_or_journey_id)
            if journey is not None:
                emergency = {"risk_score": journey.get("risk_score", 0), "trigger_reasons": journey.get("trigger_reasons", [])}
    if emergency is None:
        return {"risk_score": 0, "risk_level": "LOW", "trigger_reasons": []}
    score = max(0, min(100, int(emergency.get("risk_score", 0))))
    reasons = list(emergency.get("trigger_reasons", []) or [])
    return {"risk_score": score, "risk_level": level_for_score(score), "trigger_reasons": reasons}


def update_risk(emergency, signal_type, reason=None, delta=0):
    score = int(emergency.get("risk_score", 0))
    reasons = list(emergency.get("trigger_reasons", []) or [])
    if signal_type == "MANUAL_SOS":
        score = 100
        reasons = ["Manual SOS"]
    elif signal_type == "SAFE":
        score = 0
        reasons = ["User confirmed safe"]
    else:
        if reason is not None and reason not in reasons:
            reasons.append(reason)
        score = max(0, min(100, score + int(delta)))
    emergency["risk_score"] = score
    emergency["trigger_reasons"] = reasons
    emergency["risk_level"] = level_for_score(score)
    return compute_risk(emergency)
