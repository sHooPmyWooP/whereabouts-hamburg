"""Merge analytics and leaderboard migration branches.

Revision ID: 0005_merge_analytics_leaderboard
Revises: 0004_create_analytics, 0004_add_guess_distance_meters
"""

revision = "0005_merge_analytics_leaderboard"
down_revision = ("0004_create_analytics", "0004_add_guess_distance_meters")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
