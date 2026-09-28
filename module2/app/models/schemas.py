from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field

IncidentType = Literal["accident","road_closure","fire","flooding","protest","crime","traffic","other"]

class LatLon(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class Incident(BaseModel):
    id: str
    type: IncidentType = "other"
    title: str
    description: str = ""
    latitude: float
    longitude: float
    published_at: datetime
    severity: float = Field(0.5, ge=0, le=1)
    source: str = "demo"
    confidence: float = Field(0.8, ge=0, le=1)

class IncidentReport(BaseModel):
    type: IncidentType = "other"
    title: str
    description: str = ""
    latitude: float
    longitude: float
    severity: float = 0.5

class SearchRequest(BaseModel):
    start: LatLon
    destination: LatLon

class StartRequest(BaseModel):
    route_id: str

class RecalcRequest(BaseModel):
    journey_id: str

class SwitchRequest(BaseModel):
    alternative_route_id: str

class InjectRequest(BaseModel):
    journey_id: Optional[str] = None
    type: IncidentType = "accident"
    severity: float = 0.9
    ahead_meters: float = 600
    title: str = "Traffic accident ahead"

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
