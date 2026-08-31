"""Create admin roles and privacy-conscious analytics storage.

Revision ID: 0004_create_analytics
Revises: 0003_create_training
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_create_analytics"
down_revision: str | None = "0003_create_training"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "account", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "game_daily_districts", sa.Column("finish_reason", sa.String(16), nullable=True)
    )
    op.create_table(
        "analytics_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("visitor_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "ix_analytics_event_occurred_type",
        "analytics_event",
        ["occurred_at", "event_type"],
    )
    op.create_index("ix_analytics_event_visitor", "analytics_event", ["visitor_id"])
    op.create_index("ix_analytics_event_account", "analytics_event", ["account_id"])
    op.create_table(
        "visitor_account_link",
        sa.Column("visitor_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("visitor_id"),
    )
    op.create_index(
        "ix_visitor_account_link_account_id",
        "visitor_account_link",
        ["account_id"],
    )
    op.create_table(
        "analytics_daily_aggregate",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("analytics_daily_aggregate")
    op.drop_index(
        "ix_visitor_account_link_account_id", table_name="visitor_account_link"
    )
    op.drop_table("visitor_account_link")
    op.drop_index("ix_analytics_event_account", table_name="analytics_event")
    op.drop_index("ix_analytics_event_visitor", table_name="analytics_event")
    op.drop_index("ix_analytics_event_occurred_type", table_name="analytics_event")
    op.drop_table("analytics_event")
    op.drop_column("game_daily_districts", "finish_reason")
    op.drop_column("account", "last_login_at")
    op.drop_column("account", "is_admin")
