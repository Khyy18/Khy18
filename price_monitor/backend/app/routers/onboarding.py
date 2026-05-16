"""Роутер онбординга."""

from fastapi import APIRouter, Depends

from app.db.models import User
from app.middleware.auth import get_current_user
from app.services.onboarding_service import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/steps")
async def get_onboarding_steps(user: User = Depends(get_current_user)):
    """Получить шаги онбординга с прогрессом пользователя."""
    completed = getattr(user, "onboarding_completed_steps", None) or []
    return {
        "steps": onboarding_service.get_steps(completed),
        "current_step": onboarding_service.get_current_step(completed),
        "is_completed": onboarding_service.is_completed(completed),
    }


@router.post("/complete/{step_id}")
async def complete_step(step_id: int, user: User = Depends(get_current_user)):
    """Отметить шаг как выполненный."""
    completed = getattr(user, "onboarding_completed_steps", None) or []
    if step_id not in completed:
        completed.append(step_id)
    # В реальной реализации - сохранить в БД
    return {"completed": completed, "is_completed": onboarding_service.is_completed(completed)}
