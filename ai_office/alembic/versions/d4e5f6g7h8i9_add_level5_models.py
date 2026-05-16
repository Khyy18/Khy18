"""add level5 models

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-05-16 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("settings_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id"),
    )
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    # Add workspace_id to existing tables
    op.add_column(
        "agents", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_agents_workspace_id", "agents", "workspaces", ["workspace_id"], ["id"]
    )
    op.add_column(
        "tasks", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_tasks_workspace_id", "tasks", "workspaces", ["workspace_id"], ["id"]
    )
    op.add_column(
        "activity_logs", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_activity_logs_workspace_id",
        "activity_logs",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )
    op.add_column(
        "plans", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_plans_workspace_id", "plans", "workspaces", ["workspace_id"], ["id"]
    )
    op.add_column(
        "delegation_traces", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_delegation_traces_workspace_id",
        "delegation_traces",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )
    op.add_column(
        "task_templates", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_task_templates_workspace_id",
        "task_templates",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )
    op.add_column(
        "feedback", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_feedback_workspace_id", "feedback", "workspaces", ["workspace_id"], ["id"]
    )
    op.add_column(
        "token_usage", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_token_usage_workspace_id",
        "token_usage",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_token_usage_workspace_id", "token_usage", type_="foreignkey")
    op.drop_column("token_usage", "workspace_id")
    op.drop_constraint("fk_feedback_workspace_id", "feedback", type_="foreignkey")
    op.drop_column("feedback", "workspace_id")
    op.drop_constraint(
        "fk_task_templates_workspace_id", "task_templates", type_="foreignkey"
    )
    op.drop_column("task_templates", "workspace_id")
    op.drop_constraint(
        "fk_delegation_traces_workspace_id", "delegation_traces", type_="foreignkey"
    )
    op.drop_column("delegation_traces", "workspace_id")
    op.drop_constraint("fk_plans_workspace_id", "plans", type_="foreignkey")
    op.drop_column("plans", "workspace_id")
    op.drop_constraint(
        "fk_activity_logs_workspace_id", "activity_logs", type_="foreignkey"
    )
    op.drop_column("activity_logs", "workspace_id")
    op.drop_constraint("fk_tasks_workspace_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "workspace_id")
    op.drop_constraint("fk_agents_workspace_id", "agents", type_="foreignkey")
    op.drop_column("agents", "workspace_id")
    op.drop_table("system_settings")
    op.drop_table("workspaces")
