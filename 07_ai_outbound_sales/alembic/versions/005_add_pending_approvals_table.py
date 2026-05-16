"""Add pending_approvals table

Revision ID: 005
Revises: 004
Create Date: 2024-01-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leads.id"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
        sa.Column("proposed_response", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "expired", name="approvalstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pending_approvals_lead_id", "pending_approvals", ["lead_id"])
    op.create_index("ix_pending_approvals_status", "pending_approvals", ["status"])


def downgrade() -> None:
    op.drop_table("pending_approvals")
    op.execute("DROP TYPE IF EXISTS approvalstatus")
