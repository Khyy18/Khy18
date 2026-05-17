from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BirthData(BaseModel):
    date: str = Field(..., description="Birth date in YYYY-MM-DD format")
    time: str = Field(..., description="Birth time in HH:MM format")
    lat: float = Field(..., description="Latitude of birth place")
    lon: float = Field(..., description="Longitude of birth place")
    city: str = Field(..., description="City name of birth place")


class NatalChart(BaseModel):
    planets: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Planet positions: {planet: {sign, degree, house}}",
    )
    houses: dict[str, str] = Field(
        default_factory=dict,
        description="House cusps: {house_number: sign}",
    )
    ascendant: str = Field(default="", description="Ascendant sign")
    mc: str = Field(default="", description="Midheaven sign")
    aspects: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of aspects: [{planet1, planet2, aspect_type, orb}]",
    )


class CallStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    ACTIVE = "active"
    ENDED = "ended"


class UserSession(BaseModel):
    user_id: str
    session_id: str
    balance: int = 0
    start_time: Optional[datetime] = None
    status: CallStatus = CallStatus.IDLE
    natal_chart: Optional[NatalChart] = None


class BillingEvent(BaseModel):
    event_type: str
    user_id: str
    session_id: str
    amount: int = 0
    balance_after: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionStartRequest(BaseModel):
    user_id: str
    birth_data: BirthData
    balance: int = Field(default=100, ge=0)


class SessionStartResponse(BaseModel):
    session_id: str
    natal_chart: NatalChart
    balance: int


class BalanceTopupRequest(BaseModel):
    user_id: str
    amount: int = Field(..., gt=0)


class BalanceTopupResponse(BaseModel):
    user_id: str
    new_balance: int
