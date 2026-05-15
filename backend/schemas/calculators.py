"""Calculator request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class SalaryCalculateRequest(BaseModel):
    oklad: float = Field(..., gt=0, description="Base salary (must be positive)")
    rate: float = Field(..., gt=0, description="Employment rate (must be positive)")
    stazh_percent: float = Field(default=0, ge=0, description="Seniority bonus percent")
    category_percent: float = Field(default=0, ge=0, description="Category bonus percent")


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
    total_12_months: float = Field(..., gt=0, description="Total earnings for 12 months")
    days: int = Field(..., gt=0, description="Number of vacation days")


class VacationCalculateResponse(BaseModel):
    total_12_months: float
    avg_monthly: float
    avg_daily: float
    days: int
    vacation_gross: float
    ndfl: float
    vacation_net: float


class SickCalculateRequest(BaseModel):
    earnings_2y: float = Field(..., gt=0, description="Earnings for 2 years")
    stazh_bracket: Literal["<5", "5-8", ">8"] = Field(
        ..., description="Seniority bracket: '<5', '5-8', or '>8'"
    )
    days: int = Field(..., gt=0, description="Number of sick days")


class SickCalculateResponse(BaseModel):
    stazh_bracket: str
    percent: float
    earnings_2y: float
    daily: float
    days: int
    total_gross: float
    ndfl: float
    total_net: float
