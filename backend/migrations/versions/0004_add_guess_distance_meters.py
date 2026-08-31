"""Add exact metric distances for leaderboard scoring.

Revision ID: 0004_add_guess_distance_meters
Revises: 0003_create_training
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_guess_distance_meters"
down_revision = "0003_create_training"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guess", sa.Column("distance_meters", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("guess", "distance_meters")
