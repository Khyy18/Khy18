"""Pydantic v2 схемы для request/response API."""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class AgentResponse(BaseModel):
    """Ответ с информацией об агенте."""

    id: int
    name: str
    role: str
    status: str
    current_task_id: Optional[int] = None

    model_config = {"from_attributes": True}


class TaskResponse(BaseModel):
    """Ответ с информацией о задаче."""

    id: int
    description: str
    creator_type: str
    creator_id: str
    executor_id: Optional[int] = None
    status: str
    priority: str
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    """Схема создания задачи."""

    description: str
    priority: str = Field(default="medium", description="Приоритет задачи")
    executor_id: Optional[int] = Field(default=None, description="ID исполнителя")


class TaskUpdate(BaseModel):
    """Схема обновления задачи."""

    status: Optional[str] = None
    executor_id: Optional[int] = None


class ActivityResponse(BaseModel):
    """Ответ с информацией о записи активности."""

    id: int
    agent_id: int
    agent_name: Optional[str] = None
    action_type: str
    action_description: str
    timestamp: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel, Generic[T]):
    """Пагинированный ответ."""

    items: List[T]
    total: int
    limit: int
    offset: int
