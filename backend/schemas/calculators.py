"""Calculator request/response schemas."""

from pydantic import BaseModel


class SalaryCalculateRequest(BaseModel):
    oklad: float
    rate: float
    stazh_percent: float
    category_percent: float = 0


class SalaryCalculateResponse(BaseModel):
    nachisleno: float
    ndfl: float
    pfr: float
    oms: float
    fss: float
    fss_ns: float
    total_contributions: float
    na_ruki: float


class VacationCalculateRequest(BaseModel):
    total_12_months: float
    days: int


class VacationCalculateResponse(BaseModel):
    total_12_months: float
    avg_monthly: float
    avg_daily: float
    days: int
    vacation_gross: float
    ndfl: float
    vacation_net: float


class SickCalculateRequest(BaseModel):
    earnings_2y: float
    stazh_bracket: str  # '<5', '5-8', '>8'
    days: int


class SickCalculateResponse(BaseModel):
    stazh_bracket: str
    percent: float
    earnings_2y: float
    daily: float
    days: int
    total_gross: float
    ndfl: float
    total_net: float
