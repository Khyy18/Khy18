"""Эндпоинты для работы с задачами."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import PaginatedResponse, TaskCreate, TaskResponse, TaskUpdate
from ai_office.core.database import get_session
from ai_office.core.models import Task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=PaginatedResponse[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(default=None, description="Фильтр по статусу"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Получить список задач с фильтрацией и пагинацией."""
    query = select(Task)
    count_query = select(func.count(Task.id))

    if status:
        query = query.where(Task.status == status)
        count_query = count_query.where(Task.status == status)

    # Общее количество
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Результаты с пагинацией
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    tasks = result.scalars().all()

    return PaginatedResponse(
        items=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать новую задачу."""
    task = Task(
        description=task_data.description,
        priority=task_data.priority,
        executor_id=task_data.executor_id,
        creator_type="user",
        creator_id="api",
        status="open",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Обновить статус или исполнителя задачи."""
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task_data.status is not None:
        task.status = task_data.status
    if task_data.executor_id is not None:
        task.executor_id = task_data.executor_id

    await session.commit()
    await session.refresh(task)
    return task
