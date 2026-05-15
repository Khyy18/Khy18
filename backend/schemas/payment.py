"""Payment order schemas."""

from pydantic import BaseModel, Field


class PaymentOrderRequest(BaseModel):
    child_id: int
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2000, le=2100, description="Year")
    attendance_days: int = Field(..., gt=0, le=31, description="Attendance days")


class PaymentOrderResponse(BaseModel):
    child_id: int
    month: int
    year: int
    attendance_days: int
    amount_due: float
    discount_percent: float
    amount_after_discount: float
