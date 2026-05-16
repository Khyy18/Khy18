"""Reminder schemas."""

from typing import Optional

from pydantic import BaseModel


class ReminderToggleRequest(BaseModel):
    reminder_id: int
    enabled: bool


class ReminderResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    cron_type: Optional[str] = None
    day_of_month: Optional[int] = None
    enabled: int
    chat_id: Optional[int] = None

    model_config = {"from_attributes": True}
