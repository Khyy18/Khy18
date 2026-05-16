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


class PlanStepResponse(BaseModel):
    """Ответ с информацией о шаге плана."""

    id: int
    plan_id: int
    step_number: int
    description: str
    status: str
    result: Optional[str] = None

    model_config = {"from_attributes": True}


class PlanResponse(BaseModel):
    """Ответ с информацией о плане."""

    id: int
    goal: str
    agent_id: Optional[int] = None
    status: str
    created_at: Optional[datetime] = None
    steps: List[PlanStepResponse] = []

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    """Ответ с метриками для дашборда."""

    tasks_today: int = 0
    tasks_week_history: list[int] = []
    cost_today: float = 0.0
    cost_week_history: list[float] = []
    avg_response_ms: int = 0
    response_time_history: list[int] = []
    response_time_estimated: bool = True
    active_agents: int = 0
    hourly_activity: list[int] = []


class TemplateResponse(BaseModel):
    """Ответ с информацией о шаблоне задачи."""

    id: int
    name: str
    description_template: str
    default_priority: str
    default_executor_name: Optional[str] = None
    category: str
    icon: str

    model_config = {"from_attributes": True}


class FeedbackCreate(BaseModel):
    """Схема создания обратной связи."""

    user_telegram_id: int
    agent_name: str
    message_id: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    is_positive: Optional[bool] = None
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Ответ с информацией об обратной связи."""

    id: int
    user_telegram_id: int
    agent_name: str
    rating: Optional[int] = None
    is_positive: Optional[bool] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FeedbackStatsResponse(BaseModel):
    """Статистика обратной связи по агенту."""

    agent_name: str
    avg_rating: Optional[float] = None
    total_count: int
    positive_percentage: float


class DelegationTraceResponse(BaseModel):
    """Ответ с трассировкой делегирования."""

    id: int
    source_agent: str
    target_agent: str
    task_id: Optional[int] = None
    messages: list
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
