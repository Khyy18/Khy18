"""Модели базы данных для AI Office."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_office.core.database import Base


class Workspace(Base):
    """Модель рабочего пространства (мультитенантность)."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    settings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SystemSetting(Base):
    """Модель системных настроек."""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )


class Plan(Base):
    """Модель плана с пошаговым выполнением."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )

    # Связи
    steps: Mapped[list["PlanStep"]] = relationship(
        back_populates="plan", lazy="selectin", order_by="PlanStep.step_number"
    )

    def __repr__(self) -> str:
        return f"<Plan(id={self.id}, goal='{self.goal[:30]}', status='{self.status}')>"


class PlanStep(Base):
    """Модель шага плана."""

    __tablename__ = "plan_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    step_number: Mapped[int] = mapped_column()
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Связи
    plan: Mapped["Plan"] = relationship(back_populates="steps")

    def __repr__(self) -> str:
        return f"<PlanStep(id={self.id}, plan_id={self.plan_id}, step={self.step_number}, status='{self.status}')>"


class Agent(Base):
    """Модель агента (Alice, Sam и другие)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(200))
    system_prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="idle")
    current_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", use_alter=True), nullable=True
    )
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )

    # Связи
    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        back_populates="agent", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name='{self.name}', role='{self.role}')>"


class Task(Base):
    """Модель задачи для агентов."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    creator_type: Mapped[str] = mapped_column(String(50))  # 'user' или 'agent'
    creator_id: Mapped[str] = mapped_column(String(100))
    executor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )
    sla_target_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, status='{self.status}', priority='{self.priority}')>"


class ActivityLog(Base):
    """Лог активности агентов."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"))
    action_type: Mapped[str] = mapped_column(String(100))
    action_description: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )

    # Связи
    agent: Mapped["Agent"] = relationship(back_populates="activity_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityLog(id={self.id}, agent_id={self.agent_id}, action='{self.action_type}')>"


class TokenUsage(Base):
    """Учёт использования токенов LLM."""

    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(default=0.0)
    agent_name: Mapped[str] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )


class User(Base):
    """Модель пользователя с ролевой моделью доступа."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(50), server_default="viewer")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DelegationTrace(Base):
    """Трассировка делегирований между агентами."""

    __tablename__ = "delegation_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_agent: Mapped[str] = mapped_column(String(100))
    target_agent: Mapped[str] = mapped_column(String(100))
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    messages_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )


class TaskTemplate(Base):
    """Шаблон задачи для быстрого создания."""

    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description_template: Mapped[str] = mapped_column(Text)
    default_priority: Mapped[str] = mapped_column(String(20), default="medium")
    default_executor_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    category: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(50))
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )


class Feedback(Base):
    """Обратная связь пользователей по работе агентов."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger)
    agent_name: Mapped[str] = mapped_column(String(100))
    message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(nullable=True)
    is_positive: Mapped[Optional[bool]] = mapped_column(nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )


class ApprovalRequest(Base):
    """Запрос на одобрение критического действия."""

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    action_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )


class KnowledgeFact(Base):
    """Факт в графе знаний (тройка: субъект-предикат-объект)."""

    __tablename__ = "knowledge_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(300))
    predicate: Mapped[str] = mapped_column(String(200))
    object_value: Mapped[str] = mapped_column(String(500))
    source_agent: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditEntry(Base):
    """Запись аудита для compliance."""

    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(20))  # user/agent/system
    actor_id: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
