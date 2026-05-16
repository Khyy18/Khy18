"""Эндпоинты для шаринга карточек результатов."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import ShareCardResponse
from ai_office.core.database import get_session
from ai_office.core.share_cards import generate_task_card

router = APIRouter(prefix="/api/share", tags=["share"])


@router.get("/task/{task_id}", response_model=ShareCardResponse)
async def share_task_card(
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить карточку задачи для шаринга."""
    card = await generate_task_card(task_id, session)
    return ShareCardResponse(**card)
