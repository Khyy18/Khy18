"""Salary calculation endpoint."""

from fastapi import APIRouter

from backend.config import settings
from backend.schemas.calculators import SalaryCalculateRequest, SalaryCalculateResponse

router = APIRouter(prefix="/salary", tags=["calculators"])


def calculate_salary(
    oklad: float, rate: float, stazh_percent: float, category_percent: float = 0
) -> dict:
    """Calculate salary breakdown - same logic as bot's calculate_salary."""
    nachisleno = oklad * rate * (1 + stazh_percent / 100 + category_percent / 100)
    ndfl = nachisleno * settings.NDFL_RATE
    pfr = nachisleno * settings.PFR_RATE
    oms = nachisleno * settings.OMS_RATE
    fss = nachisleno * settings.FSS_RATE
    fss_ns = nachisleno * settings.FSS_NS_RATE
    total_contributions = pfr + oms + fss + fss_ns
    na_ruki = nachisleno - ndfl
    return {
        "nachisleno": nachisleno,
        "ndfl": ndfl,
        "pfr": pfr,
        "oms": oms,
        "fss": fss,
        "fss_ns": fss_ns,
        "total_contributions": total_contributions,
        "na_ruki": na_ruki,
    }


@router.post("/calculate", response_model=SalaryCalculateResponse)
async def salary_calculate(data: SalaryCalculateRequest):
    result = calculate_salary(data.oklad, data.rate, data.stazh_percent, data.category_percent)
    return result
