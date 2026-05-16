"""Reminders endpoints."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.database import get_db
from backend.models.reminder import Reminder
from backend.schemas.reminder import ReminderResponse, ReminderToggleRequest

# Deadlines data (same as bot)
DEADLINES = [
    {
        "name": "6-NDFL",
        "description": "Raschet summ naloga na dokhody fizicheskikh lits",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [4, 7, 10, 1],
    },
    {
        "name": "RSV",
        "description": "Raschet po strakhovym vznosam",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [1, 4, 7, 10],
    },
    {
        "name": "SZV-M (EFS-1)",
        "description": "Svedeniya o zastrakhovannykh litsakh",
        "recurrence": "monthly",
        "day_of_month": 15,
        "months": list(range(1, 13)),
    },
    {
        "name": "Zarplata (avans)",
        "description": "Vyplata avansa sotrudnikam",
        "recurrence": "monthly",
        "day_of_month": 25,
        "months": list(range(1, 13)),
    },
    {
        "name": "Zarplata (raschet)",
        "description": "Vyplata zarabotnoj platy",
        "recurrence": "monthly",
        "day_of_month": 10,
        "months": list(range(1, 13)),
    },
    {
        "name": "NDFL (perechislenie)",
        "description": "Perechislenie NDFL v byudzhet",
        "recurrence": "monthly",
        "day_of_month": 28,
        "months": list(range(1, 13)),
    },
    {
        "name": "Strakhovye vznosy",
        "description": "Perechislenie strakhovykh vznosov (PFR, OMS, FSS)",
        "recurrence": "monthly",
        "day_of_month": 28,
        "months": list(range(1, 13)),
    },
    {
        "name": "Nalog na imushchestvo",
        "description": "Avansovyj platezh po nalogu na imushchestvo",
        "recurrence": "quarterly",
        "day_of_month": 28,
        "months": [4, 7, 10, 3],
    },
    {
        "name": "4-FSS",
        "description": "Raschet po vznosam na travmatizm",
        "recurrence": "quarterly",
        "day_of_month": 25,
        "months": [1, 4, 7, 10],
    },
    {
        "name": "Roditelskaya plata",
        "description": "Sbor roditelskoj platy za soderzhanie rebyonka",
        "recurrence": "monthly",
        "day_of_month": 20,
        "months": list(range(1, 13)),
    },
]

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=List[ReminderResponse])
async def list_reminders(
    chat_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Reminder)
    if chat_id is not None:
        query = query.where(Reminder.chat_id == chat_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/toggle", response_model=ReminderResponse)
async def toggle_reminder(
    data: ReminderToggleRequest,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    result = await db.execute(select(Reminder).where(Reminder.id == data.reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        # Create a new reminder stub
        reminder = Reminder(id=data.reminder_id, name="custom", enabled=int(data.enabled))
        db.add(reminder)
    else:
        reminder.enabled = int(data.enabled)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.get("/upcoming")
async def upcoming_deadlines():
    """Return next upcoming deadlines within 30 days."""
    today = date.today()
    upcoming = []
    for dl in DEADLINES:
        for month in dl["months"]:
            try:
                deadline_date = date(today.year, month, dl["day_of_month"])
            except ValueError:
                continue
            diff = (deadline_date - today).days
            if 0 <= diff <= 30:
                upcoming.append({
                    "name": dl["name"],
                    "description": dl["description"],
                    "date": deadline_date.isoformat(),
                    "days_left": diff,
                })
    upcoming.sort(key=lambda x: x["days_left"])
    return upcoming
