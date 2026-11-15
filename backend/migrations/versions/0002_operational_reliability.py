"""Targeting rules, guarded rollouts, health samples and Kafka dead letters.

Revision ID: 0002_operational_reliability
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_operational_reliability"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("flags", sa.Column("targeting_json", sa.Text(), nullable=False, server_default="{}"))
    op.create_table(
        "guard_policies",
        sa.Column("flag_id", sa.String(36), sa.ForeignKey("flags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("max_error_rate", sa.Float(), nullable=False),
        sa.Column("max_p95_ms", sa.Integer(), nullable=False),
        sa.Column("min_samples", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("consecutive_windows", sa.Integer(), nullable=False),
    )
    op.create_table(
        "feature_health_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("flag_id", sa.String(36), sa.ForeignKey("flags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("error", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feature_health_samples_flag_id", "feature_health_samples", ["flag_id"])
    op.create_index("ix_feature_health_samples_created_at", "feature_health_samples", ["created_at"])
    op.create_table(
        "event_dead_letters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("topic", sa.String(150), nullable=False),
        sa.Column("partition", sa.Integer(), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(250), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("topic", "partition", "offset", name="uq_dlq_position"),
    )


def downgrade():
    op.drop_table("event_dead_letters")
    op.drop_index("ix_feature_health_samples_created_at", table_name="feature_health_samples")
    op.drop_index("ix_feature_health_samples_flag_id", table_name="feature_health_samples")
    op.drop_table("feature_health_samples")
    op.drop_table("guard_policies")
    op.drop_column("flags", "targeting_json")
