"""Модели базы данных для AI Office."""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_office.core.database import Base


class Agent(Base):
    """Модель агента (Alice, Sam и другие)."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(200))
    system_prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="idle")
    current_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
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

    # Связи
    agent: Mapped["Agent"] = relationship(back_populates="activity_logs")

    def __repr__(self) -> str:
        return f"<ActivityLog(id={self.id}, agent_id={self.agent_id}, action='{self.action_type}')>"
