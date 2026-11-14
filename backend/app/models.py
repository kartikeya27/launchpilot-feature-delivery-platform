from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def utcnow():
    return datetime.now(timezone.utc)

class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (UniqueConstraint("key", "environment", name="uq_key_env"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(72), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    environment: Mapped[str] = mapped_column(String(16), default="production")
    owner: Mapped[str] = mapped_column(String(80), default="Platform team")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout: Mapped[int] = mapped_column(Integer, default=0)
    salt: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Exposure(Base):
    __tablename__ = "exposures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flag_id: Mapped[str] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    user_hash: Mapped[str] = mapped_column(String(64), index=True)
    served: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

class Conversion(Base):
    __tablename__ = "conversions"
    __table_args__ = (UniqueConstraint("flag_id", "user_hash", name="uq_conversion_user_flag"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flag_id: Mapped[str] = mapped_column(ForeignKey("flags.id", ondelete="CASCADE"), index=True)
    user_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flag_id: Mapped[str] = mapped_column(String(36), index=True)
    flag_key: Mapped[str] = mapped_column(String(72))
    action: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(80), default="demo-admin")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EventOutbox(Base):
    __tablename__ = "event_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic: Mapped[str] = mapped_column(String(150))
    payload_json: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EventReceipt(Base):
    __tablename__ = "event_receipts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
