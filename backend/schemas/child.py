"""Child schemas."""

from typing import Optional

from pydantic import BaseModel


class ChildCreate(BaseModel):
    child_fio: str
    group_name: str
    parent_fio: str
    discount_percent: float = 0


class ChildResponse(BaseModel):
    id: int
    child_fio: str
    group_name: str
    parent_fio: str
    discount_percent: float
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}
