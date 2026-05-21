"""Initial migration - создание всех таблиц

Revision ID: 001_initial
Revises: None
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица пользователей
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("balance", sa.Numeric(precision=12, scale=2), server_default="0.00"),
        sa.Column("referred_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # Таблица сессий
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Enum("active", "finished", name="sessionstatus"), server_default="active"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=2), server_default="0.00"),
        sa.Column("rate_per_minute", sa.Numeric(precision=10, scale=2), server_default="5.00"),
    )

    # Таблица транзакций
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("type", sa.Enum("deposit", "debit", name="transactiontype"), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("status", sa.Enum("pending", "completed", "failed", name="transactionstatus"), server_default="completed"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Таблица промокодов
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("code", sa.String(), unique=True, nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="1"),
        sa.Column("current_uses", sa.Integer(), server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])

    # Таблица подписок
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan", sa.Enum("free", "basic", "premium", name="subscriptionplan"), server_default="free"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), server_default="false"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    # Таблица заметок по сессиям
    op.create_table(
        "session_notes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("homework", sa.Text(), nullable=True),
        sa.Column("mood_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_session_notes_session_id", "session_notes", ["session_id"])


def downgrade() -> None:
    op.drop_table("session_notes")
    op.drop_table("subscriptions")
    op.drop_table("promo_codes")
    op.drop_table("transactions")
    op.drop_table("sessions")
    op.drop_table("users")
