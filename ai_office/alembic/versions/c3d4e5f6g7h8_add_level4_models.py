"""add level4 models

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-16 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "delegation_traces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_agent", sa.String(length=100), nullable=False),
        sa.Column("target_agent", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("messages_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description_template", sa.Text(), nullable=False),
        sa.Column("default_priority", sa.String(length=20), nullable=False),
        sa.Column("default_executor_name", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("is_positive", sa.Boolean(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("feedback")
    op.drop_table("task_templates")
    op.drop_table("delegation_traces")
