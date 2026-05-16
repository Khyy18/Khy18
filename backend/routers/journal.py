"""Journal endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.database import get_db
from backend.models.journal import JournalEntry
from backend.schemas.journal import JournalEntryCreate, JournalEntryResponse

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post("", response_model=JournalEntryResponse, status_code=201)
async def add_entry(
    data: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_bearer_token),
):
    entry = JournalEntry(
        date=data.date,
        amount=data.amount,
        entry_type=data.entry_type,
        counterparty=data.counterparty,
        basis=data.basis,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("", response_model=List[JournalEntryResponse])
async def list_entries(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(JournalEntry)
    if start_date:
        query = query.where(JournalEntry.date >= start_date)
    if end_date:
        query = query.where(JournalEntry.date <= end_date)
    result = await db.execute(query.order_by(JournalEntry.date.desc()))
    return result.scalars().all()


@router.get("/totals")
async def journal_totals(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Period totals: sum of income and expense."""
    query = select(JournalEntry)
    if start_date:
        query = query.where(JournalEntry.date >= start_date)
    if end_date:
        query = query.where(JournalEntry.date <= end_date)
    result = await db.execute(query)
    entries = result.scalars().all()
    income = sum(e.amount for e in entries if e.entry_type == "income")
    expense = sum(e.amount for e in entries if e.entry_type == "expense")
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
    }
