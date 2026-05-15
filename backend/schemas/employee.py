"""Employee schemas."""

from typing import Optional

from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    fio: str
    position: str
    rate: float = Field(default=1.0, gt=0, description="Employment rate (must be positive)")


class EmployeeResponse(BaseModel):
    id: int
    fio: str
    position: str
    rate: float
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}
