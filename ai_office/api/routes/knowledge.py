"""Эндпоинты для графа знаний."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import KnowledgeFactCreate, KnowledgeFactResponse
from ai_office.core.database import get_session
from ai_office.core.models import KnowledgeFact

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeFactResponse])
async def query_knowledge(
    entity: Optional[str] = Query(default=None, description="Поиск по субъекту или объекту"),
    session: AsyncSession = Depends(get_session),
):
    """Запросить факты из графа знаний."""
    query = select(KnowledgeFact)
    if entity:
        query = query.where(
            or_(
                KnowledgeFact.subject.contains(entity),
                KnowledgeFact.object_value.contains(entity),
            )
        )
    query = query.order_by(KnowledgeFact.created_at.desc())
    result = await session.execute(query)
    items = result.scalars().all()
    return [KnowledgeFactResponse.model_validate(item) for item in items]


@router.post("", response_model=KnowledgeFactResponse, status_code=201)
async def add_fact(
    body: KnowledgeFactCreate,
    session: AsyncSession = Depends(get_session),
):
    """Добавить факт в граф знаний."""
    fact = KnowledgeFact(
        subject=body.subject,
        predicate=body.predicate,
        object_value=body.object_value,
        source_agent=body.source_agent,
        confidence=body.confidence,
    )
    session.add(fact)
    await session.commit()
    await session.refresh(fact)
    return KnowledgeFactResponse.model_validate(fact)


@router.delete("/{fact_id}")
async def delete_fact(
    fact_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Удалить факт из графа знаний."""
    result = await session.execute(
        select(KnowledgeFact).where(KnowledgeFact.id == fact_id)
    )
    fact = result.scalar_one_or_none()
    if fact is None:
        raise HTTPException(status_code=404, detail="Факт не найден")

    await session.delete(fact)
    await session.commit()
    return {"status": "deleted", "id": fact_id}
