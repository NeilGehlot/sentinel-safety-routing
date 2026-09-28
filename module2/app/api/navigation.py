import uuid
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from app.config import settings
from app.models.schemas import Incident, InjectRequest, StartRequest, SwitchRequest, utcnow
from app.services import navigation_service as nav, store
from app.services.geo import point_at

router = APIRouter(prefix="/api", tags=["navigation"])

def _j(jid):
    if jid not in store.journeys:
        raise HTTPException(404, "Unknown journey")
    return store.journeys[jid]

@router.post("/navigation/start")
def start(req: StartRequest):
    if req.route_id not in store.routes:
        raise HTTPException(404, "Unknown route")
    return {"journey_id": nav.start(req.route_id)}

@router.get("/navigation/{jid}/status")
def status(jid: str):
    _j(jid); return nav.status(jid)

@router.post("/navigation/{jid}/switch")
def switch(jid: str, req: SwitchRequest):
    _j(jid)
    if req.alternative_route_id not in store.routes:
        raise HTTPException(404, "Unknown route")
    return nav.switch(jid, req.alternative_route_id)

@router.post("/navigation/{jid}/dismiss")
def dismiss(jid: str):
    _j(jid); nav.dismiss(jid); return {"ok": True}

@router.get("/navigation/{jid}/location")
def location(jid: str):
    _j(jid); s = nav.status(jid)
    return {"journey_id": jid, "position": s["position"], "status": s["status"]}

@router.get("/navigation/{jid}/route-context")
def context(jid: str):
    _j(jid); s = nav.status(jid)
    return {k: s[k] for k in ("journey_id", "position", "eta_min", "safety", "status", "incidents_ahead", "next_checkpoint", "geometry")}

@router.post("/demo/inject-incident")
def inject(req: InjectRequest):
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE is disabled")
    if not req.journey_id:
        raise HTTPException(422, "journey_id required")
    j = _j(req.journey_id); r = store.routes[j["route_id"]]
    lat, lon = point_at(r["geometry"], j["progress"] + req.ahead_meters)
    inc = Incident(id="DEMO"+uuid.uuid4().hex[:5], type=req.type, title=req.title, latitude=lat, longitude=lon,
                   description="Injected demo incident", published_at=utcnow()-timedelta(minutes=5),
                   severity=req.severity, source="demo", confidence=0.9)
    store.incidents.append(inc)
    return inc
