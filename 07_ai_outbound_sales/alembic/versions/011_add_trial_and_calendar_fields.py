"""Add trial and calendar fields to tenants table

Revision ID: 011
Revises: 010
Create Date: 2024-01-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add trial-related columns to tenants table
    op.add_column(
        "tenants",
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("trial_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "is_trial", sa.Boolean, server_default="false", nullable=False
        ),
    )

    # Add per-tenant calendar configuration
    op.add_column(
        "tenants",
        sa.Column("calendar_config", JSONB, nullable=True),
    )

    # Add voice_calls_used to trials table for trial voice limit tracking
    op.add_column(
        "trials",
        sa.Column("voice_calls_used", sa.Integer, server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("trials", "voice_calls_used")
    op.drop_column("tenants", "calendar_config")
    op.drop_column("tenants", "is_trial")
    op.drop_column("tenants", "trial_expires_at")
    op.drop_column("tenants", "trial_started_at")
