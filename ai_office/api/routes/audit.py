"""Эндпоинты для аудита."""

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import AuditEntryResponse
from ai_office.core.database import get_session
from ai_office.core.models import AuditEntry

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryResponse])
async def list_audit_entries(
    actor_type: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    resource_type: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Получить записи аудита с фильтрацией и пагинацией."""
    query = select(AuditEntry)

    if actor_type:
        query = query.where(AuditEntry.actor_type == actor_type)
    if action:
        query = query.where(AuditEntry.action == action)
    if resource_type:
        query = query.where(AuditEntry.resource_type == resource_type)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.where(AuditEntry.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.where(AuditEntry.timestamp <= dt_to)
        except ValueError:
            pass

    query = query.order_by(AuditEntry.timestamp.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = result.scalars().all()
    return [AuditEntryResponse.model_validate(item) for item in items]


@router.get("/export")
async def export_audit(
    format: str = Query(default="csv"),
    session: AsyncSession = Depends(get_session),
):
    """Экспорт записей аудита в CSV или JSON."""
    result = await session.execute(
        select(AuditEntry).order_by(AuditEntry.timestamp.desc()).limit(1000)
    )
    entries = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "workspace_id", "actor_type", "actor_id",
            "action", "resource_type", "resource_id",
            "details_json", "ip_address", "timestamp",
        ])
        for entry in entries:
            writer.writerow([
                entry.id, entry.workspace_id, entry.actor_type,
                entry.actor_id, entry.action, entry.resource_type,
                entry.resource_id, entry.details_json,
                entry.ip_address, entry.timestamp,
            ])
        return PlainTextResponse(
            content=output.getvalue(),
            media_type="text/csv",
        )

    # JSON structured report
    return {
        "report_type": "audit_export",
        "total_entries": len(entries),
        "entries": [
            AuditEntryResponse.model_validate(e).model_dump()
            for e in entries
        ],
    }
