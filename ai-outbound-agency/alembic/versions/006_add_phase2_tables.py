"""Add api_keys, webhooks tables and brand_settings column on tenants

Revision ID: 006
Revises: 005
Create Date: 2024-01-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add brand_settings JSONB column to tenants table
    op.add_column(
        "tenants",
        sa.Column("brand_settings", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=True),
    )

    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # Create webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("events", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("secret", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_webhooks_tenant_id", "webhooks", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("webhooks")
    op.drop_table("api_keys")
    op.drop_column("tenants", "brand_settings")
