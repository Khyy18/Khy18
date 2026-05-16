"""Initial schema - trades, rejected_signals, rejected_checks, equity_curve, kv_store.

Revision ID: 001_initial
Revises:
Create Date: 2025-01-16

Схема соответствует текущей структуре memory.py.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("exit", sa.Float(), nullable=True),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("ema", sa.Float(), nullable=True),
        sa.Column("rsi", sa.Float(), nullable=True),
        sa.Column("atr", sa.Float(), nullable=True),
        sa.Column("ai_reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False, server_default="OPEN"),
        sa.Column("closed_ts", sa.Text(), nullable=True),
    )

    op.create_table(
        "rejected_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "rejected_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("filter", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("indicators_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "equity_curve",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.Text(), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("hwm", sa.Float(), nullable=False),
        sa.Column("drawdown", sa.Float(), nullable=False),
    )

    op.create_table(
        "kv_store",
        sa.Column("k", sa.Text(), primary_key=True),
        sa.Column("v", sa.Text(), nullable=False),
        sa.Column("updated_ts", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("kv_store")
    op.drop_table("equity_curve")
    op.drop_table("rejected_checks")
    op.drop_table("rejected_signals")
    op.drop_table("trades")
