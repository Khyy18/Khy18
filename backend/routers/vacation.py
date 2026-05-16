"""Vacation calculation endpoint."""

from fastapi import APIRouter

from backend.config import settings
from backend.schemas.calculators import VacationCalculateRequest, VacationCalculateResponse

router = APIRouter(prefix="/vacation", tags=["calculators"])


def calculate_vacation(total_12_months: float, days: int) -> dict:
    """Calculate vacation pay - same logic as bot's calculate_vacation."""
    avg_monthly = total_12_months / 12
    avg_daily = total_12_months / 12 / settings.AVG_DAYS_MONTH
    vacation_gross = avg_daily * days
    ndfl = vacation_gross * settings.NDFL_RATE
    vacation_net = vacation_gross - ndfl
    return {
        "total_12_months": total_12_months,
        "avg_monthly": avg_monthly,
        "avg_daily": avg_daily,
        "days": days,
        "vacation_gross": vacation_gross,
        "ndfl": ndfl,
        "vacation_net": vacation_net,
    }


@router.post("/calculate", response_model=VacationCalculateResponse)
async def vacation_calculate(data: VacationCalculateRequest):
    result = calculate_vacation(data.total_12_months, data.days)
    return result
