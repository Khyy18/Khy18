"""Payment order schemas."""

from pydantic import BaseModel


class PaymentOrderRequest(BaseModel):
    child_id: int
    month: int
    year: int
    attendance_days: int


class PaymentOrderResponse(BaseModel):
    child_id: int
    month: int
    year: int
    attendance_days: int
    amount_due: float
    discount_percent: float
    amount_after_discount: float
