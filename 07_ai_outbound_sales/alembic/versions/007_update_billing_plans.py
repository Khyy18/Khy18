"""Update billing plans: add domains_limit, rename scale to agency

Revision ID: 007
Revises: 006
Create Date: 2024-01-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add domains_limit column with default 1
    op.add_column(
        "plans",
        sa.Column("domains_limit", sa.Integer(), nullable=False, server_default="1"),
    )

    # Update the planname enum: rename 'scale' to 'agency'
    # For PostgreSQL, alter the enum type
    op.execute("ALTER TYPE planname RENAME VALUE 'scale' TO 'agency'")

    # Update plan data to reflect new tiers
    op.execute(
        "UPDATE plans SET domains_limit = 1 WHERE name = 'starter'"
    )
    op.execute(
        "UPDATE plans SET domains_limit = 3 WHERE name = 'growth'"
    )
    op.execute(
        "UPDATE plans SET domains_limit = -1 WHERE name = 'agency'"
    )
    op.execute(
        "UPDATE plans SET domains_limit = -1 WHERE name = 'enterprise'"
    )

    # Update pricing to match SaaS tiers
    op.execute(
        "UPDATE plans SET leads_limit = 500, emails_limit = 1000, "
        "linkedin_limit = 0, campaigns_limit = 1, price_cents = 9900 "
        "WHERE name = 'starter'"
    )
    op.execute(
        "UPDATE plans SET leads_limit = 2000, emails_limit = 5000, "
        "linkedin_limit = 500, campaigns_limit = 5, price_cents = 29900 "
        "WHERE name = 'growth'"
    )
    op.execute(
        "UPDATE plans SET leads_limit = 10000, emails_limit = 25000, "
        "linkedin_limit = 2000, campaigns_limit = -1, price_cents = 79900 "
        "WHERE name = 'agency'"
    )


def downgrade() -> None:
    # Revert enum rename
    op.execute("ALTER TYPE planname RENAME VALUE 'agency' TO 'scale'")

    # Remove domains_limit column
    op.drop_column("plans", "domains_limit")
