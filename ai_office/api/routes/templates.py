"""Эндпоинты для шаблонов задач."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import TaskResponse, TemplateResponse
from ai_office.api.websocket import broadcast_event
from ai_office.core.database import get_session
from ai_office.core.models import Agent, Task, TaskTemplate

router = APIRouter(prefix="/api", tags=["templates"])

# Default templates for seeding
DEFAULT_TEMPLATES = [
    {
        "name": "Code Review",
        "description_template": "Провести ревью кода: {описание}",
        "default_priority": "medium",
        "default_executor_name": "sam",
        "category": "dev",
        "icon": "code",
    },
    {
        "name": "Bug Fix",
        "description_template": "Исправить баг: {описание}",
        "default_priority": "high",
        "default_executor_name": "sam",
        "category": "dev",
        "icon": "bug",
    },
    {
        "name": "Design Review",
        "description_template": "Ревью дизайна: {описание}",
        "default_priority": "medium",
        "default_executor_name": "max",
        "category": "design",
        "icon": "palette",
    },
    {
        "name": "Write Tests",
        "description_template": "Написать тесты для: {описание}",
        "default_priority": "medium",
        "default_executor_name": "leo",
        "category": "qa",
        "icon": "shield",
    },
    {
        "name": "Deploy to Production",
        "description_template": "Деплой в продакшен: {описание}",
        "default_priority": "high",
        "default_executor_name": "nova",
        "category": "devops",
        "icon": "rocket",
    },
    {
        "name": "SEO Audit",
        "description_template": "SEO аудит: {описание}",
        "default_priority": "low",
        "default_executor_name": "iris",
        "category": "marketing",
        "icon": "search",
    },
    {
        "name": "Budget Report",
        "description_template": "Подготовить финансовый отчёт: {описание}",
        "default_priority": "medium",
        "default_executor_name": "oscar",
        "category": "finance",
        "icon": "calculator",
    },
    {
        "name": "Create User Story",
        "description_template": "Создать user story: {описание}",
        "default_priority": "medium",
        "default_executor_name": "alice",
        "category": "pm",
        "icon": "clipboard",
    },
]


async def seed_templates(session: AsyncSession):
    """Заполнить таблицу шаблонов дефолтными значениями, если она пуста."""
    global _templates_seeded
    if _templates_seeded:
        return
    count_result = await session.execute(select(func.count(TaskTemplate.id)))
    count = count_result.scalar() or 0
    if count == 0:
        for tmpl_data in DEFAULT_TEMPLATES:
            tmpl = TaskTemplate(**tmpl_data)
            session.add(tmpl)
        await session.commit()
    _templates_seeded = True


def reset_templates_seeded():
    """Reset the seeding flag (used in tests with fresh DBs)."""
    global _templates_seeded
    _templates_seeded = False


# Module-level flag: once templates are seeded, skip the DB check on subsequent calls
_templates_seeded = False


@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    session: AsyncSession = Depends(get_session),
):
    """Получить список шаблонов задач."""
    await seed_templates(session)
    result = await session.execute(select(TaskTemplate))
    templates = result.scalars().all()
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post("/tasks/from-template/{template_id}", response_model=TaskResponse, status_code=201)
async def create_task_from_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Создать задачу из шаблона."""
    result = await session.execute(
        select(TaskTemplate).where(TaskTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    # Find executor by name if specified
    executor_id = None
    if template.default_executor_name:
        agent_result = await session.execute(
            select(Agent).where(
                Agent.name.ilike(template.default_executor_name)
            )
        )
        agent = agent_result.scalar_one_or_none()
        if agent:
            executor_id = agent.id

    task = Task(
        description=template.description_template,
        creator_type="user",
        creator_id="template",
        executor_id=executor_id,
        status="open",
        priority=template.default_priority,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await broadcast_event("new_task", {
        "id": task.id,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
    })
    return task
