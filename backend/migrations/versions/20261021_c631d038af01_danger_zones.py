"""Danger zones and per-camera zone timing overrides.

Revision ID: c631d038af01
Revises: b452b4c88e6b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c631d038af01"
down_revision = "b452b4c88e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zones",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("camera_id", sa.UUID(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("points", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("jsonb_typeof(points) = 'array' AND jsonb_array_length(points) BETWEEN 3 AND 64", name="points_count"),
    )
    op.create_index("ix_zones_camera_id", "zones", ["camera_id"])
    for name in ("zone_enter_dwell_seconds", "zone_exit_grace_seconds", "event_cooldown_seconds"):
        op.add_column("camera_configs", sa.Column(name, sa.Float(), nullable=True))
        op.create_check_constraint(f"{name}_range", "camera_configs", f"{name} >= 0 AND {name} <= 3600")


def downgrade() -> None:
    for name in ("zone_enter_dwell_seconds", "zone_exit_grace_seconds", "event_cooldown_seconds"):
        op.drop_constraint(op.f(f"ck_camera_configs_{name}_range"), "camera_configs", type_="check")
        op.drop_column("camera_configs", name)
    op.drop_table("zones")
