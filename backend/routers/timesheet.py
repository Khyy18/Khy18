"""Timesheet endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.database import get_db
from backend.models.timesheet import TimesheetMark
from backend.schemas.timesheet import TimesheetMarkCreate, TimesheetMarkResponse

router = APIRouter(prefix="/timesheet", tags=["timesheet"])


@router.post("/mark", response_model=TimesheetMarkResponse, status_code=201)
async def add_mark(
    data: TimesheetMarkCreate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    mark = TimesheetMark(
        employee_id=data.employee_id,
        date=data.date,
        mark_type=data.mark_type,
    )
    db.add(mark)
    await db.commit()
    await db.refresh(mark)
    return mark


@router.get("/summary/{employee_id}")
async def timesheet_summary(
    employee_id: int,
    year: int = Query(...),
    month: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Monthly summary: count marks by type for given employee/month."""
    date_prefix = f"{year:04d}-{month:02d}"
    result = await db.execute(
        select(TimesheetMark.mark_type, func.count(TimesheetMark.id))
        .where(
            TimesheetMark.employee_id == employee_id,
            TimesheetMark.date.like(f"{date_prefix}%"),
        )
        .group_by(TimesheetMark.mark_type)
    )
    rows = result.all()
    summary = {row[0]: row[1] for row in rows}
    return {"employee_id": employee_id, "year": year, "month": month, "summary": summary}
