"""add multitenancy

Revision ID: c3d4e5f6g7h8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17 01:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('settings_json', sa.Text(), nullable=True),
        sa.Column('plan_name', sa.String(length=50), nullable=False, server_default='trial'),
        sa.Column('stripe_customer_id', sa.String(length=100), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='member'),
        sa.Column('is_super_admin', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )

    # Create tenant_agents table
    op.create_table(
        'tenant_agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('agent_name', sa.String(length=100), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('custom_config_json', sa.Text(), nullable=True),
        sa.Column('memory_usage_bytes', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Add tenant_id to existing tables (SQLite compat with batch)
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_tasks_tenant_id', 'tenants', ['tenant_id'], ['id'])

    with op.batch_alter_table('activity_logs') as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_activity_logs_tenant_id', 'tenants', ['tenant_id'], ['id'])

    with op.batch_alter_table('plans') as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_plans_tenant_id', 'tenants', ['tenant_id'], ['id'])

    with op.batch_alter_table('plan_steps') as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_plan_steps_tenant_id', 'tenants', ['tenant_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('plan_steps') as batch_op:
        batch_op.drop_constraint('fk_plan_steps_tenant_id', type_='foreignkey')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('plans') as batch_op:
        batch_op.drop_constraint('fk_plans_tenant_id', type_='foreignkey')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('activity_logs') as batch_op:
        batch_op.drop_constraint('fk_activity_logs_tenant_id', type_='foreignkey')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_constraint('fk_tasks_tenant_id', type_='foreignkey')
        batch_op.drop_column('tenant_id')

    op.drop_table('tenant_agents')
    op.drop_table('users')
    op.drop_table('tenants')
