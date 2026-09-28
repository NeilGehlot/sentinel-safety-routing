"""Deterministic reroute policy. RAG/LLM output never feeds this decision."""
from app.config import settings
from app.services import route_matcher, route_scorer

def evaluate(routing, current, progress_m, position, dest, incidents):
    speed = current["distance_m"]/current["duration_s"]
    eff = route_matcher.match(current["geometry"], incidents, progress_m, speed)
    cur = route_scorer.score(current["geometry"], eff)
    remaining_min = (current["distance_m"] - progress_m)/speed/60
    res = {"current_safety": cur["safety"], "base_safety": cur["base_safety"], "effects": eff,
           "factors": cur["factors"], "remaining_min": remaining_min, "recommended": False,
           "alternative": None, "reasons": []}
    if not eff or cur["safety"] >= settings.critical:
        return res
    best = None
    for r in routing.routes(position, dest):
        m = route_matcher.match(r["geometry"], incidents, 0, r["distance_m"]/r["duration_s"])
        s = route_scorer.score(r["geometry"], m)
        r.update(safety=s["safety"], factors=s["factors"], eta_min=r["duration_s"]/60)
        if best is None or r["safety"] > best["safety"]:
            best = r
    if not best:
        return res
    improve = best["safety"] - cur["safety"]
    extra = best["eta_min"] - remaining_min
    res["alternative"] = best
    res.update(improvement=round(improve, 1), extra_minutes=round(extra, 1))
    if improve >= settings.min_improve and extra <= settings.max_extra:
        n = eff[0]
        res["recommended"] = True
        res["reasons"] = [
            f"Incident detected {round(n['distance_ahead_m'])} m ahead",
            f"Reported {round(n['age_min'])} minutes ago",
            f"Estimated arrival: {round(n['eta_min'])} minutes",
            f"Current safety: {cur['base_safety']:.0f} → {cur['safety']:.0f}",
            f"Alternative improves safety by {improve:.0f} points",
            f"Alternative adds {max(extra, 0):.0f} minutes"]
    return res
