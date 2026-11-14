"""Initial PostgreSQL schema with events/outbox and audit trail.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("flags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(72), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("rollout", sa.Integer(), nullable=False),
        sa.Column("salt", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", "environment", name="uq_key_env"))
    op.create_index("ix_flags_key", "flags", ["key"])
    op.create_table("exposures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("flag_id", sa.String(36), sa.ForeignKey("flags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_hash", sa.String(64), nullable=False),
        sa.Column("served", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for name in ("flag_id", "user_hash", "created_at"):
        op.create_index(f"ix_exposures_{name}", "exposures", [name])
    op.create_table("conversions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("flag_id", sa.String(36), sa.ForeignKey("flags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("flag_id", "user_hash", name="uq_conversion_user_flag"))
    op.create_index("ix_conversions_flag_id", "conversions", ["flag_id"])
    op.create_table("audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("flag_id", sa.String(36), nullable=False),
        sa.Column("flag_key", sa.String(72), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_logs_flag_id", "audit_logs", ["flag_id"])
    op.create_table("event_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("topic", sa.String(150), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("event_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_event_receipts_event_id", "event_receipts", ["event_id"], unique=True)

def downgrade():
    op.drop_table("event_receipts")
    op.drop_table("event_outbox")
    op.drop_table("audit_logs")
    op.drop_table("conversions")
    op.drop_table("exposures")
    op.drop_table("flags")
