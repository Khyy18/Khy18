"""Add objections table for objection library

Revision ID: 013
Revises: 012
Create Date: 2024-01-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "objections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("objection_text", sa.Text, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("responses", JSONB, server_default="[]"),
        sa.Column("times_encountered", sa.Integer, server_default="1"),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_index("ix_objections_tenant_id", "objections", ["tenant_id"])
    op.create_index("ix_objections_category", "objections", ["category"])


def downgrade() -> None:
    op.drop_index("ix_objections_category", table_name="objections")
    op.drop_index("ix_objections_tenant_id", table_name="objections")
    op.drop_table("objections")
