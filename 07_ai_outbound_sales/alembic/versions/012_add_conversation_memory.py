"""Add lead_interactions table and conversation_context to leads

Revision ID: 012
Revises: 011
Create Date: 2024-01-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create lead_interactions table
    op.create_table(
        "lead_interactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False
        ),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("interaction_type", sa.String, nullable=False),
        sa.Column("channel", sa.String, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("context_json", JSONB, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Add indexes
    op.create_index(
        "ix_lead_interactions_lead_id", "lead_interactions", ["lead_id"]
    )
    op.create_index(
        "ix_lead_interactions_tenant_id", "lead_interactions", ["tenant_id"]
    )

    # Add conversation_context column to leads table
    op.add_column(
        "leads",
        sa.Column("conversation_context", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "conversation_context")
    op.drop_index("ix_lead_interactions_tenant_id", table_name="lead_interactions")
    op.drop_index("ix_lead_interactions_lead_id", table_name="lead_interactions")
    op.drop_table("lead_interactions")
