"""Employee schemas."""

from typing import Optional

from pydantic import BaseModel


class EmployeeCreate(BaseModel):
    fio: str
    position: str
    rate: float = 1.0


class EmployeeResponse(BaseModel):
    id: int
    fio: str
    position: str
    rate: float
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}
