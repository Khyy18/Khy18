"""Production calendar endpoint."""

from calendar import monthrange

from fastapi import APIRouter, HTTPException

from backend.data.production_calendar import WORKING_DAYS, HOLIDAYS

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/{year}/{month}")
async def get_month_info(year: int, month: int):
    """Return working days, holidays, and weekend info for a given month."""
    if year not in WORKING_DAYS or month not in WORKING_DAYS.get(year, {}):
        raise HTTPException(status_code=404, detail="Data not available for this period")

    total_days = monthrange(year, month)[1]
    working_days = WORKING_DAYS[year][month]
    holidays = HOLIDAYS.get(year, {}).get(month, [])
    weekend_days = total_days - working_days - len(holidays)

    return {
        "year": year,
        "month": month,
        "working_days": working_days,
        "holidays": holidays,
        "total_days": total_days,
        "weekend_days": weekend_days,
    }
