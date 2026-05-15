"""Journal entry schemas."""

from typing import Optional, Literal

from pydantic import BaseModel, Field


class JournalEntryCreate(BaseModel):
    date: str
    amount: float = Field(..., gt=0, description="Amount (must be positive)")
    entry_type: Literal["income", "expense"] = Field(
        ..., description="Entry type: 'income' or 'expense'"
    )
    counterparty: Optional[str] = None
    basis: Optional[str] = None


class JournalEntryResponse(BaseModel):
    id: int
    date: str
    amount: float
    entry_type: str
    counterparty: Optional[str] = None
    basis: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}
