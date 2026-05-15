"""Journal entry schemas."""

from typing import Optional

from pydantic import BaseModel


class JournalEntryCreate(BaseModel):
    date: str
    amount: float
    entry_type: str  # 'income' or 'expense'
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
