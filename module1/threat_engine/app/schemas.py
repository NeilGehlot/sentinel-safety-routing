"""Pydantic v2 contracts for POST /v1/assess and GET /v1/health."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Activity(StrEnum):
    STATIONARY = "stationary"
    WALKING = "walking"
    RUNNING = "running"
    VEHICLE = "vehicle"
    FALL = "fall"
    SUDDEN_STOP = "sudden_stop"


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float
    lon: float
    speed_mps: float | None = None
    heading_deg: float | None = None


class DeviceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    battery_pct: float
    cellular_dbm: float
    internet_available: bool


class NearbyDevices(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ble_count: int
    wifi_count: int


class Movement(BaseModel):
    """An accelerometer window, or a precomputed activity when no window is sent.

    sudden_stop is allowed here as a precomputed activity. A speed drop can
    still derive the same label when the request does not send it.
    """

    model_config = ConfigDict(extra="forbid")

    accel_window: list[list[float]] | None = None
    sampling_hz: float | None = None
    activity: Activity | None = None


class AssessRequest(BaseModel):
    """POST /v1/assess body. Only location and timestamp are required."""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    timestamp: datetime
    location: Location
    device: DeviceState | None = None
    nearby_devices: NearbyDevices | None = None
    movement: Movement | None = None


class PredictedScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_min: int
    score: int = Field(ge=0, le=100)


class Contributor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: str
    points: int
    reason: str


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    contributors: list[Contributor]


class AssessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    current_score: int = Field(ge=0, le=100)
    predicted: list[PredictedScore]
    explanation: Explanation
    recommendations: list[str]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
