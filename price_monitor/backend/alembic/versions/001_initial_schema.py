"""Initial schema with all models.

Revision ID: 001_initial
Revises: None
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("is_vip", sa.Boolean(), default=False),
        sa.Column("vip_expires_at", sa.DateTime(), nullable=True),
        sa.Column("interests", sa.Text(), default="[]"),
        sa.Column("referral_code", sa.String(), nullable=True),
        sa.Column("fcm_token", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("referral_code"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("marketplace", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("rating", sa.Float(), default=0.0),
        sa.Column("reviews_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("old_price", sa.Float(), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("is_fraud", sa.Boolean(), default=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("max_price", sa.Float(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), default="RUB"),
        sa.Column("status", sa.String(), default="pending"),
        sa.Column("plan", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_payment_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "partners",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel_name", sa.String(), nullable=False),
        sa.Column("channel_url", sa.String(), nullable=True),
        sa.Column("widget_code", sa.String(), nullable=False),
        sa.Column("commission_percent", sa.Float(), default=5.0),
        sa.Column("total_clicks", sa.Integer(), default=0),
        sa.Column("total_conversions", sa.Integer(), default=0),
        sa.Column("balance", sa.Float(), default=0.0),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("widget_code"),
    )

    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("short_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("partner_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("converted", sa.Boolean(), default=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("variant", sa.String(), nullable=True),
        sa.Column("impressions", sa.Integer(), default=0),
        sa.Column("clicks", sa.Integer(), default=0),
        sa.Column("ctr", sa.Float(), default=0.0),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "short_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("short_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("affiliate_url", sa.String(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_id"),
    )

    op.create_table(
        "push_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "arbitrage_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_wb_id", sa.Integer(), nullable=True),
        sa.Column("product_ozon_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("price_wb", sa.Float(), nullable=False),
        sa.Column("price_ozon", sa.Float(), nullable=False),
        sa.Column("diff_percent", sa.Float(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("found_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_wb_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["product_ozon_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("is_fake", sa.Boolean(), default=False),
        sa.Column("fake_score", sa.Float(), default=0.0),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "niche_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("growth_percent", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=True),
        sa.Column("product_count", sa.Integer(), default=0),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "seller_copies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "content_scripts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("script_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "badges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("badge_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("earned_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("badges")
    op.drop_table("content_scripts")
    op.drop_table("seller_copies")
    op.drop_table("niche_analyses")
    op.drop_table("reviews")
    op.drop_table("arbitrage_results")
    op.drop_table("push_logs")
    op.drop_table("short_links")
    op.drop_table("chat_messages")
    op.drop_table("posts")
    op.drop_table("clicks")
    op.drop_table("partners")
    op.drop_table("payments")
    op.drop_table("favorites")
    op.drop_table("alerts")
    op.drop_table("price_history")
    op.drop_table("products")
    op.drop_table("users")
