"""Sick leave calculation endpoint."""

from fastapi import APIRouter

from backend.config import settings
from backend.schemas.calculators import SickCalculateRequest, SickCalculateResponse

router = APIRouter(prefix="/sick", tags=["calculators"])


def calculate_sick(earnings_2y: float, stazh_bracket: str, days: int) -> dict:
    """Calculate sick leave pay - same logic as bot's calculate_sick."""
    if stazh_bracket == "<5":
        percent = 0.60
    elif stazh_bracket == "5-8":
        percent = 0.80
    else:
        percent = 1.00

    daily = (earnings_2y / 730) * percent
    total_gross = daily * days
    ndfl = total_gross * settings.NDFL_RATE
    total_net = total_gross - ndfl

    return {
        "stazh_bracket": stazh_bracket,
        "percent": percent,
        "earnings_2y": earnings_2y,
        "daily": daily,
        "days": days,
        "total_gross": total_gross,
        "ndfl": ndfl,
        "total_net": total_net,
    }


@router.post("/calculate", response_model=SickCalculateResponse)
async def sick_calculate(data: SickCalculateRequest):
    result = calculate_sick(data.earnings_2y, data.stazh_bracket, data.days)
    return result
