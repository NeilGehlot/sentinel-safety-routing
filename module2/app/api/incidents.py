import uuid
from fastapi import APIRouter
from app.models.schemas import Incident, IncidentReport, utcnow
from app.services import store

router = APIRouter(prefix="/api", tags=["incidents"])

@router.get("/incidents/recent")
def recent(limit: int = 50):
    return sorted(store.incidents, key=lambda i: i.published_at, reverse=True)[:limit]

@router.post("/incidents/report", response_model=Incident)
def report(r: IncidentReport):
    inc = Incident(id="USR"+uuid.uuid4().hex[:6], published_at=utcnow(), source="user", confidence=0.6, **r.model_dump())
    store.incidents.append(inc)
    return inc
