"""Journal endpoints."""

import io
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_bearer_token
from backend.config import settings
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


class JournalExportRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/export-excel")
async def export_journal_excel(
    data: JournalExportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Export journal entries to Excel."""
    query = select(JournalEntry)
    if data.start_date:
        query = query.where(JournalEntry.date >= data.start_date)
    if data.end_date:
        query = query.where(JournalEntry.date <= data.end_date)
    result = await db.execute(query.order_by(JournalEntry.date.desc()))
    entries = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "\u0416\u0443\u0440\u043d\u0430\u043b"

    headers = [
        "\u0414\u0430\u0442\u0430",
        "\u0422\u0438\u043f",
        "\u0421\u0443\u043c\u043c\u0430",
        "\u041a\u043e\u043d\u0442\u0440\u0430\u0433\u0435\u043d\u0442",
        "\u041e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435",
    ]
    ws.append(headers)

    total_income = 0.0
    total_expense = 0.0

    for entry in entries:
        entry_type_label = "\u0414\u043e\u0445\u043e\u0434" if entry.entry_type == "income" else "\u0420\u0430\u0441\u0445\u043e\u0434"
        ws.append([
            entry.date,
            entry_type_label,
            entry.amount,
            entry.counterparty or "",
            entry.basis or "",
        ])
        if entry.entry_type == "income":
            total_income += entry.amount
        else:
            total_expense += entry.amount

    ws.append([])
    ws.append(["\u0418\u0442\u043e\u0433\u043e \u0434\u043e\u0445\u043e\u0434", "", total_income, "", ""])
    ws.append(["\u0418\u0442\u043e\u0433\u043e \u0440\u0430\u0441\u0445\u043e\u0434", "", total_expense, "", ""])
    ws.append(["\u0411\u0430\u043b\u0430\u043d\u0441", "", total_income - total_expense, "", ""])

    ws.protection.sheet = True
    ws.protection.password = settings.EXCEL_PASSWORD

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=journal.xlsx"},
    )
