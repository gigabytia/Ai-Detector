"""Per-camera detection configuration.

Revision ID: b452b4c88e6b
Revises: a43b43e08e6b
"""
from alembic import op
import sqlalchemy as sa

revision = "b452b4c88e6b"
down_revision = "a43b43e08e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_configs",
        sa.Column("camera_id", sa.UUID(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("target_fps", sa.Float(), nullable=True),
        sa.Column("detection_confidence", sa.Float(), nullable=True),
        sa.CheckConstraint("target_fps >= 1 AND target_fps <= 30", name="target_fps_range"),
        sa.CheckConstraint("detection_confidence > 0 AND detection_confidence <= 1", name="confidence_range"),
    )


def downgrade() -> None:
    op.drop_table("camera_configs")
