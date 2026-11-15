"""Read-only operational status and explicit, audit-logged flag rollback.

Queue counts are global across environments. They do not imply Kafka broker health.
"""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .auth import Principal, admin, viewer
from .cache import invalidate_flag
from .db import get_db
from .models import AuditLog, EventOutbox, EventReceipt, Flag
from .schemas import Environment, FlagOut

router = APIRouter(prefix="/api/operations", tags=["Release operations"])


class RollbackRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=200)


def configuration(flag: Flag) -> dict:
    return {
        "name": flag.name, "owner": flag.owner, "description": flag.description,
        "enabled": flag.enabled, "rollout": flag.rollout, "version": flag.version,
    }


@router.get("/overview")
def operations_overview(
    environment: Environment = "staging",
    db: Session = Depends(get_db),
    _user: Principal = Depends(viewer),
):
    flags = db.scalars(
        select(Flag).where(Flag.environment == environment).order_by(Flag.created_at).limit(100)
    ).all()
    pending = db.scalar(select(func.count()).select_from(EventOutbox).where(EventOutbox.published_at.is_(None))) or 0
    published = db.scalar(select(func.count()).select_from(EventOutbox).where(EventOutbox.published_at.is_not(None))) or 0
    ingested = db.scalar(select(func.count()).select_from(EventReceipt)) or 0
    oldest = db.scalar(select(func.min(EventOutbox.created_at)).where(EventOutbox.published_at.is_(None)))
    if oldest and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    pending_age = max(0, int((datetime.now(timezone.utc) - oldest).total_seconds())) if oldest else None
    return {
        "environment": environment,
        "flags": [
            {"id": f.id, "key": f.key, "name": f.name, "enabled": f.enabled,
             "rollout": f.rollout, "version": f.version}
            for f in flags
        ],
        "pipeline": {
            "transport": os.getenv("EVENT_TRANSPORT", "disabled"),
            "pending": pending, "published": published, "ingested": ingested,
            "oldest_pending_seconds": pending_age,
            "scope": "global",
            "broker_health": "not_measured",
        },
    }


@router.post("/flags/{flag_id}/rollback", response_model=FlagOut)
def rollback_flag(
    flag_id: str,
    request: RollbackRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(admin),
):
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(404, detail="Flag not found")
    if flag.version != request.version:
        raise HTTPException(409, detail="Flag changed since it was loaded. Refresh and retry.")
    previous = configuration(flag)
    result = db.execute(
        update(Flag)
        .where(Flag.id == flag_id, Flag.version == request.version)
        .values(enabled=False, rollout=0, version=Flag.version + 1, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, detail="Concurrent flag change. Refresh and retry.")
    db.refresh(flag)
    after = {**configuration(flag), "reason": request.reason}
    db.add(AuditLog(
        id=str(uuid4()), flag_id=flag.id, flag_key=flag.key,
        action="rollback", actor=user.subject,
        before_json=json.dumps(previous), after_json=json.dumps(after),
    ))
    db.commit()
    invalidate_flag(flag.key, flag.environment)
    return flag
