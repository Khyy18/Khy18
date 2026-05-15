"""Payment order generation endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.config import settings
from backend.database import get_db
from backend.models.child import Child
from backend.schemas.payment import PaymentOrderRequest, PaymentOrderResponse

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/generate", response_model=PaymentOrderResponse)
async def generate_payment(
    data: PaymentOrderRequest,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    """Generate payment order for parent fee."""
    result = await db.execute(select(Child).where(Child.id == data.child_id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    amount_due = data.attendance_days * settings.BASE_FEE_PER_DAY
    discount = child.discount_percent or 0
    amount_after_discount = amount_due * (1 - discount / 100)

    return PaymentOrderResponse(
        child_id=data.child_id,
        month=data.month,
        year=data.year,
        attendance_days=data.attendance_days,
        amount_due=amount_due,
        discount_percent=discount,
        amount_after_discount=amount_after_discount,
    )
