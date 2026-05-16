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


class AdminAgentUpdate(BaseModel):
    """Схема обновления агента (для админ-панели)."""

    system_prompt: Optional[str] = None
    enabled: Optional[bool] = None


class SystemSettingResponse(BaseModel):
    """Ответ с информацией о системной настройке."""

    id: int
    key: str
    value: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SystemSettingUpdate(BaseModel):
    """Схема обновления системной настройки."""

    value: str


class WorkspaceResponse(BaseModel):
    """Ответ с информацией о рабочем пространстве."""

    id: int
    telegram_chat_id: int
    name: str
    owner_telegram_id: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class IntegrationTestRequest(BaseModel):
    """Запрос на тестирование интеграции."""

    integration_type: str
    api_key: str


class IntegrationTestResponse(BaseModel):
    """Ответ на тестирование интеграции."""

    success: bool
    message: str


class ApprovalRequestResponse(BaseModel):
    """Ответ с информацией о запросе на одобрение."""

    id: int
    agent_name: str
    action_type: str
    description: str
    metadata_json: Optional[str] = None
    status: str
    requested_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by_user_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ApprovalResolveRequest(BaseModel):
    """Схема разрешения запроса на одобрение."""

    approved: bool
    user_id: int = 0


class SLAStatusResponse(BaseModel):
    """Ответ со статусом SLA."""

    compliance_percent: float
    avg_response_by_priority: dict
    breaches_count: int
    total_monitored: int


class AnalyticsOverviewResponse(BaseModel):
    """Ответ с обзором аналитики."""

    tasks_completed_week: int
    tasks_completed_month: int
    avg_time_to_resolve: dict
    agent_workload: list
    bottleneck_agent: Optional[str] = None
    throughput_trend: list


class AgentAnalyticsResponse(BaseModel):
    """Аналитика по конкретному агенту."""

    agent_name: str
    tasks_completed: int
    avg_response_time: float
    delegation_count: int
    feedback_score: Optional[float] = None
    sla_compliance_percent: float


class ProductivityResponse(BaseModel):
    """Ответ с метриками продуктивности команды."""

    created_vs_completed: list
    peak_hours: list
    most_used_templates: list


class AuditEntryResponse(BaseModel):
    """Ответ с записью аудита."""

    id: int
    workspace_id: Optional[int] = None
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details_json: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KnowledgeFactResponse(BaseModel):
    """Ответ с фактом из графа знаний."""

    id: int
    subject: str
    predicate: str
    object_value: str
    source_agent: str
    confidence: float
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KnowledgeFactCreate(BaseModel):
    """Схема создания факта в графе знаний."""

    subject: str
    predicate: str
    object_value: str
    source_agent: str = "user"
    confidence: float = 0.9


class BrandingConfigResponse(BaseModel):
    """Ответ с конфигурацией брендинга."""

    company_name: str = "AI Office"
    logo_url: str = ""
    accent_color: str = "#3b82f6"
    agent_names: dict = {}
    enabled_agents: list = []
    welcome_message: str = ""
    custom_css: str = ""


class BrandingConfigUpdate(BaseModel):
    """Схема обновления конфигурации брендинга."""

    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    accent_color: Optional[str] = None
    agent_names: Optional[dict] = None
    enabled_agents: Optional[list] = None
    welcome_message: Optional[str] = None
    custom_css: Optional[str] = None


class MarketplacePluginResponse(BaseModel):
    """Ответ с информацией о плагине маркетплейса."""

    id: str
    name: str
    description: str
    version: str
    author: str
    download_url: str = ""
    tools_count: int
    installed: bool = False


class ReferralStatsResponse(BaseModel):
    """Статистика реферальной программы пользователя."""

    direct_referrals: int
    level_2: int
    level_3: int
    total_bonus: int


class ReferralCodeResponse(BaseModel):
    """Ответ с реферальным кодом и ссылкой."""

    code: str
    referral_link: str


class ReferralApplyRequest(BaseModel):
    """Запрос на применение реферального кода."""

    code: str


class ReferralApplyResponse(BaseModel):
    """Ответ на применение реферального кода."""

    success: bool
    message: str
    bonus_granted: int


class ShareCardResponse(BaseModel):
    """Ответ с данными карточки задачи для шаринга."""

    task_description: str
    agent_name: str
    completed_in: str
    priority: str
    share_text: str
