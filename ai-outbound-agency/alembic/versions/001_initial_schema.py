"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Sequences
    op.create_table(
        "sequences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("steps", JSONB, server_default="[]"),
    )
    op.create_index("ix_sequences_tenant_id", "sequences", ["tenant_id"])

    # Leads
    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("linkedin_url", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("enrichment_data", JSONB, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum(
                "new", "contacted", "replied", "qualified", "booked", "lost",
                name="leadstatus",
            ),
            nullable=False,
            server_default="new",
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_status", "leads", ["status"])

    # Campaigns
    op.create_table(
        "campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("icp_filter", JSONB, server_default="{}"),
        sa.Column(
            "sequence_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sequences.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "active", "paused", "completed",
                name="campaignstatus",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    # Messages
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leads.id"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum("email", "linkedin", "twitter", name="channeltype"),
            nullable=False,
        ),
        sa.Column(
            "direction",
            sa.Enum("outbound", "inbound", name="messagedirection"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "sent", "opened", "clicked", "replied", "bounced",
                name="messagestatus",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
    )
    op.create_index("ix_messages_lead_id", "messages", ["lead_id"])
    op.create_index("ix_messages_campaign_id", "messages", ["campaign_id"])
    op.create_index("ix_messages_status", "messages", ["status"])

    # Events
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "open", "click", "reply", "bounce", "unsubscribe",
                name="eventtype",
            ),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("metadata", JSONB, server_default="{}"),
    )
    op.create_index("ix_events_message_id", "events", ["message_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("messages")
    op.drop_table("campaigns")
    op.drop_table("leads")
    op.drop_table("sequences")
    op.drop_table("tenants")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS eventtype")
    op.execute("DROP TYPE IF EXISTS messagestatus")
    op.execute("DROP TYPE IF EXISTS messagedirection")
    op.execute("DROP TYPE IF EXISTS channeltype")
    op.execute("DROP TYPE IF EXISTS campaignstatus")
    op.execute("DROP TYPE IF EXISTS leadstatus")
