"""Add voice tables (calls, call_scripts) and related enums

Revision ID: 009
Revises: 008
Create Date: 2024-01-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create callstatus enum type
    callstatus_enum = sa.Enum(
        "initiated",
        "ringing",
        "answered",
        "in_progress",
        "completed",
        "failed",
        "no_answer",
        "busy",
        name="callstatus",
    )
    callstatus_enum.create(op.get_bind(), checkfirst=True)

    # Create calloutcome enum type
    calloutcome_enum = sa.Enum(
        "qualified",
        "not_interested",
        "voicemail",
        "no_answer",
        "error",
        "busy",
        name="calloutcome",
    )
    calloutcome_enum.create(op.get_bind(), checkfirst=True)

    # Add 'voice' to channeltype enum
    op.execute("ALTER TYPE channeltype ADD VALUE IF NOT EXISTS 'voice'")

    # Create call_scripts table
    op.create_table(
        "call_scripts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("script_json", JSONB, server_default="{}"),
        sa.Column("voice_id", sa.String, nullable=True),
        sa.Column("language", sa.String, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create calls table
    op.create_table(
        "calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("campaign_id", UUID(as_uuid=True), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("twilio_sid", sa.String, nullable=True),
        sa.Column("status", callstatus_enum, nullable=False, server_default="initiated"),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recording_url", sa.String, nullable=True),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("outcome", calloutcome_enum, nullable=True),
        sa.Column("cost_cents", sa.Integer, server_default="0"),
        sa.Column("script_id", UUID(as_uuid=True), sa.ForeignKey("call_scripts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add indexes
    op.create_index("ix_calls_tenant_id", "calls", ["tenant_id"])
    op.create_index("ix_calls_lead_id", "calls", ["lead_id"])
    op.create_index("ix_calls_status", "calls", ["status"])
    op.create_index("ix_calls_campaign_id", "calls", ["campaign_id"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_calls_campaign_id", table_name="calls")
    op.drop_index("ix_calls_status", table_name="calls")
    op.drop_index("ix_calls_lead_id", table_name="calls")
    op.drop_index("ix_calls_tenant_id", table_name="calls")

    # Drop tables
    op.drop_table("calls")
    op.drop_table("call_scripts")

    # Drop enum types
    sa.Enum(name="calloutcome").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="callstatus").drop(op.get_bind(), checkfirst=True)
