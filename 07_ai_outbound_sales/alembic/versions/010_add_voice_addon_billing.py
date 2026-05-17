"""Add voice_addons table for Voice AI add-on billing

Revision ID: 010
Revises: 009
Create Date: 2024-01-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create voice addon plan enum
    voiceaddonplan_enum = sa.Enum(
        "voice_starter",
        "voice_pro",
        "voice_scale",
        name="voiceaddonplan",
    )
    voiceaddonplan_enum.create(op.get_bind(), checkfirst=True)

    # Create voice_addons table
    op.create_table(
        "voice_addons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("plan_name", voiceaddonplan_enum, nullable=False),
        sa.Column("stripe_subscription_id", sa.String, nullable=True),
        sa.Column("calls_limit", sa.Integer, nullable=False),
        sa.Column("calls_used_this_period", sa.Integer, server_default="0", nullable=False),
        sa.Column("overage_rate_cents", sa.Integer, server_default="50", nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Add indexes
    op.create_index("ix_voice_addons_tenant_id", "voice_addons", ["tenant_id"])
    op.create_index("ix_voice_addons_is_active", "voice_addons", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_voice_addons_is_active", table_name="voice_addons")
    op.drop_index("ix_voice_addons_tenant_id", table_name="voice_addons")
    op.drop_table("voice_addons")
    sa.Enum(name="voiceaddonplan").drop(op.get_bind(), checkfirst=True)
