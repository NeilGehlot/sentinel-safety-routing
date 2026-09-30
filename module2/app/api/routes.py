from fastapi import APIRouter, HTTPException
from app.models.schemas import SearchRequest, RecalcRequest
from app.services import navigation_service as nav, route_matcher, route_scorer, store
from app.services.module1_client import current_threat

router = APIRouter(prefix="/api/routes", tags=["routes"])

@router.post("/search")
def search(req: SearchRequest):
    s, d = (req.start.latitude, req.start.longitude), (req.destination.latitude, req.destination.longitude)
    found = nav.routing.routes(s, d)
    if not found:
        raise HTTPException(404, "No routes found")
    for r in found:
        eff = route_matcher.match(r["geometry"], store.incidents, 0, r["distance_m"]/r["duration_s"])
        sc = route_scorer.score(r["geometry"], eff)
        r.update(safety=sc["safety"], factors=sc["factors"], incident_count=sc["incident_count"], eta_min=round(r["duration_s"]/60, 1))
        store.routes[r["id"]] = r
    best = max(found, key=lambda x: x["safety"])
    for r in found:
        r["recommended"] = r is best
    return {"routes": found, "module1_threat": current_threat(*s)}

@router.get("/geocode")
def geocode(q: str):
    """Free-text place search via Nominatim; empty list if unreachable so the UI can fall back."""
    import httpx
    try:
        res = httpx.get("https://nominatim.openstreetmap.org/search",
                        params={"q": q, "format": "json", "limit": 5, "viewbox": "75.6,27.1,76.0,26.7"},
                        headers={"User-Agent": "sentinel-safety-routing/0.1"}, timeout=8)
        res.raise_for_status()
        return [{"name": p["display_name"], "latitude": float(p["lat"]), "longitude": float(p["lon"])} for p in res.json()]
    except (httpx.HTTPError, ValueError, KeyError):
        return []

@router.post("/recalculate")
def recalc(req: RecalcRequest):
    if req.journey_id not in store.journeys:
        raise HTTPException(404, "Unknown journey")
    return nav.status(req.journey_id)
