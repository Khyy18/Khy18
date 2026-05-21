"""Add onboarding_step column to tenants table

Revision ID: 008
Revises: 007
Create Date: 2024-01-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the onboardingstep enum type
    onboarding_step_enum = sa.Enum(
        "tenant_created",
        "smtp_connected",
        "icp_uploaded",
        "campaign_activated",
        "completed",
        name="onboardingstep",
    )
    onboarding_step_enum.create(op.get_bind(), checkfirst=True)

    # Add onboarding_step column to tenants table
    op.add_column(
        "tenants",
        sa.Column(
            "onboarding_step",
            onboarding_step_enum,
            nullable=True,
            server_default="tenant_created",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "onboarding_step")

    # Drop the enum type
    sa.Enum(name="onboardingstep").drop(op.get_bind(), checkfirst=True)
