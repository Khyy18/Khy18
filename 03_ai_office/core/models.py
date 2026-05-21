"""Модели базы данных для AI Office."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_office.core.database import Base


class Tenant(Base):
    """Модель тенанта (организации)."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    settings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_name: Mapped[str] = mapped_column(String(50), default="trial")
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="tenant", lazy="selectin")
    tenant_agents: Mapped[list["TenantAgent"]] = relationship(
        back_populates="tenant", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', plan='{self.plan_name}')>"


class User(Base):
    """Модель пользователя."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="member")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="users", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class TenantAgent(Base):
    """Модель конфигурации агента для тенанта."""

    __tablename__ = "tenant_agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    agent_name: Mapped[str] = mapped_column(String(100))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    memory_usage_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="tenant_agents", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TenantAgent(id={self.id}, tenant_id={self.tenant_id}, agent='{self.agent_name}')>"


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
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True
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
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True
    )

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
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True
    )

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
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True
    )

    # Связи
    agent: Mapped["Agent"] = relationship(back_populates="activity_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityLog(id={self.id}, agent_id={self.agent_id}, action='{self.action_type}')>"
