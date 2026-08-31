"""Backfill finish reasons for completed Daily Challenge games.

Revision ID: 0006_backfill_finish_reason
Revises: 0005_merge_analytics_leaderboard
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_backfill_finish_reason"
down_revision: str | None = "0005_merge_analytics_leaderboard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    game = sa.table(
        "game_daily_districts",
        sa.column("id", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("budget_remaining", sa.Integer()),
        sa.column("solved_pin_indices", sa.JSON()),
        sa.column("finish_reason", sa.String()),
    )
    connection = op.get_bind()
    finished_games = connection.execute(
        sa.select(
            game.c.id,
            game.c.budget_remaining,
            game.c.solved_pin_indices,
            game.c.finish_reason,
        ).where(game.c.status == "finished")
    ).all()
    for row in finished_games:
        if row.finish_reason is not None:
            continue
        solved_count = len(row.solved_pin_indices or [])
        reason = "solved" if solved_count == 5 else "budget" if row.budget_remaining == 0 else "gave_up"
        connection.execute(
            game.update()
            .where(game.c.id == row.id)
            .values(finish_reason=reason)
        )


def downgrade() -> None:
    pass
