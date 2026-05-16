"""Add A/B test tables

Revision ID: 003
Revises: 002
Create Date: 2024-01-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ab_tests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "completed", "paused", name="abteststatus"),
            nullable=False,
            server_default="running",
        ),
        sa.Column("variants", JSONB, server_default="[]"),
        sa.Column("min_sends_per_variant", sa.Integer(), server_default="100"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_variant_key", sa.String(), nullable=True),
    )
    op.create_index("ix_ab_tests_tenant_id", "ab_tests", ["tenant_id"])
    op.create_index("ix_ab_tests_campaign_id", "ab_tests", ["campaign_id"])
    op.create_index("ix_ab_tests_status", "ab_tests", ["status"])

    op.create_table(
        "ab_test_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ab_tests.id"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leads.id"),
            nullable=False,
        ),
        sa.Column("variant_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ab_test_assignments_test_id", "ab_test_assignments", ["test_id"])
    op.create_index("ix_ab_test_assignments_lead_id", "ab_test_assignments", ["lead_id"])
    op.create_index(
        "ix_ab_test_assignments_test_lead",
        "ab_test_assignments",
        ["test_id", "lead_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("ab_test_assignments")
    op.drop_table("ab_tests")
    op.execute("DROP TYPE IF EXISTS abteststatus")
