"""Add lead_feedback and competitive_intel tables

Revision ID: 006
Revises: 005
Create Date: 2024-01-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_feedbacks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leads.id"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("event_trigger", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_lead_feedbacks_tenant_id", "lead_feedbacks", ["tenant_id"])
    op.create_index("ix_lead_feedbacks_lead_id", "lead_feedbacks", ["lead_id"])

    op.create_table(
        "competitive_intel",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("competitor_name", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_competitive_intel_category", "competitive_intel", ["category"])


def downgrade() -> None:
    op.drop_table("competitive_intel")
    op.drop_table("lead_feedbacks")
