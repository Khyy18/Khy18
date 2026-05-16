"""Add billing tables

Revision ID: 004
Revises: 003
Create Date: 2024-01-04 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create plans table
    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "name",
            sa.Enum("starter", "growth", "scale", "enterprise", name="planname"),
            nullable=False,
        ),
        sa.Column("stripe_price_id", sa.String(), nullable=True),
        sa.Column("leads_limit", sa.Integer(), nullable=False),
        sa.Column("emails_limit", sa.Integer(), nullable=False),
        sa.Column("linkedin_limit", sa.Integer(), nullable=False),
        sa.Column("campaigns_limit", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_plans_name", "plans", ["name"])

    # Create subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "past_due", "canceled", "trialing", name="subscriptionstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "ix_subscriptions_stripe_customer_id",
        "subscriptions",
        ["stripe_customer_id"],
    )

    # Create usage_records table
    op.create_table(
        "usage_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leads_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("emails_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("linkedin_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "period_start", name="uq_usage_tenant_period"),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index(
        "ix_usage_records_tenant_period",
        "usage_records",
        ["tenant_id", "period_start"],
    )

    # Seed default plans
    plans_table = sa.table(
        "plans",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("stripe_price_id", sa.String()),
        sa.column("leads_limit", sa.Integer()),
        sa.column("emails_limit", sa.Integer()),
        sa.column("linkedin_limit", sa.Integer()),
        sa.column("campaigns_limit", sa.Integer()),
        sa.column("price_cents", sa.Integer()),
    )

    op.bulk_insert(
        plans_table,
        [
            {
                "id": uuid.uuid4(),
                "name": "starter",
                "stripe_price_id": None,
                "leads_limit": 500,
                "emails_limit": 1000,
                "linkedin_limit": 0,
                "campaigns_limit": 1,
                "price_cents": 9900,
            },
            {
                "id": uuid.uuid4(),
                "name": "growth",
                "stripe_price_id": None,
                "leads_limit": 2000,
                "emails_limit": 5000,
                "linkedin_limit": 500,
                "campaigns_limit": 5,
                "price_cents": 29900,
            },
            {
                "id": uuid.uuid4(),
                "name": "scale",
                "stripe_price_id": None,
                "leads_limit": 10000,
                "emails_limit": 25000,
                "linkedin_limit": 2000,
                "campaigns_limit": -1,
                "price_cents": 79900,
            },
            {
                "id": uuid.uuid4(),
                "name": "enterprise",
                "stripe_price_id": None,
                "leads_limit": -1,
                "emails_limit": -1,
                "linkedin_limit": -1,
                "campaigns_limit": -1,
                "price_cents": 0,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
    op.execute("DROP TYPE IF EXISTS planname")
