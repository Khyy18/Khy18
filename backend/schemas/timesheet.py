"""Timesheet schemas."""

from pydantic import BaseModel


class TimesheetMarkCreate(BaseModel):
    employee_id: int
    date: str
    mark_type: str


class TimesheetMarkResponse(BaseModel):
    id: int
    employee_id: int
    date: str
    mark_type: str

    model_config = {"from_attributes": True}
