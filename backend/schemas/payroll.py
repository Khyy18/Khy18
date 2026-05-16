"""Payroll request/response schemas."""

from typing import List

from pydantic import BaseModel, Field


class PayrollEmployeeInput(BaseModel):
    fio: str = Field(..., min_length=1)
    oklad: float = Field(..., gt=0)
    rate: float = Field(..., gt=0)
    stazh_percent: float = Field(default=0, ge=0)
    category_percent: float = Field(default=0, ge=0)


class PayrollEmployeeResult(BaseModel):
    fio: str
    oklad: float
    rate: float
    nachisleno: float
    ndfl: float
    pfr: float
    oms: float
    fss: float
    fss_ns: float
    na_ruki: float


class PayrollRequest(BaseModel):
    employees: List[PayrollEmployeeInput]


class PayrollResponse(BaseModel):
    employees: List[PayrollEmployeeResult]
    totals: dict
