from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BirthData(BaseModel):
    date: str = Field(..., description="Birth date in YYYY-MM-DD format")
    time: str = Field(..., description="Birth time in HH:MM format")
    lat: float = Field(..., description="Latitude of birth place")
    lon: float = Field(..., description="Longitude of birth place")
    city: str = Field(..., description="City name of birth place")
    tz_offset: float = Field(
        default=0.0,
        description="Timezone offset from UTC in hours (e.g. 3.0 for Moscow)",
    )

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date is in YYYY-MM-DD format."""
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        from datetime import datetime as dt

        try:
            dt.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date value")
        return v

    @field_validator("time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time is in HH:MM format."""
        import re

        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Time must be in HH:MM format")
        parts = v.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        if hour < 0 or hour > 23:
            raise ValueError("Hour must be between 00 and 23")
        if minute < 0 or minute > 59:
            raise ValueError("Minute must be between 00 and 59")
        return v


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
    token: str = Field(default="", description="Session token for WebSocket authentication")


class BalanceTopupRequest(BaseModel):
    user_id: str
    amount: int = Field(..., gt=0)


class BalanceTopupResponse(BaseModel):
    user_id: str
    new_balance: int
