"""Initial migration - create users, sessions, and billing_event_logs tables.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_users_telegram_id", "users", ["telegram_id"], if_not_exists=True
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("natal_chart_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        if_not_exists=True,
    )
    op.create_index(
        "ix_sessions_session_id", "sessions", ["session_id"], if_not_exists=True
    )

    op.create_table(
        "billing_event_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_billing_event_logs_session_id",
        "billing_event_logs",
        ["session_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("billing_event_logs")
    op.drop_table("sessions")
    op.drop_table("users")
