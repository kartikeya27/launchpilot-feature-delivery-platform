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
from .models import AuditLog, DeadLetterEvent, EventOutbox, EventReceipt, FeatureHealthSample, Flag, GuardPolicy
from .schemas import Environment, FlagOut, TargetingRules
from .event_validation import validate_event
from .guardrails import evaluate_guardrails

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
    dead_letters = db.scalar(select(func.count()).select_from(DeadLetterEvent).where(DeadLetterEvent.replayed_at.is_(None))) or 0
    return {
        "dead_letters": dead_letters,
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


class TargetingUpdate(BaseModel):
    version: int = Field(ge=1)
    rules: TargetingRules


@router.put("/flags/{flag_id}/targeting", response_model=FlagOut)
def set_targeting(
    flag_id: str, request: TargetingUpdate,
    db: Session = Depends(get_db), user: Principal = Depends(admin),
):
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    before = configuration(flag)
    before["targeting"] = json.loads(flag.targeting_json)
    result = db.execute(
        update(Flag).where(Flag.id == flag_id, Flag.version == request.version)
        .values(targeting_json=request.rules.model_dump_json(), version=Flag.version + 1,
                updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Stale targeting policy. Refresh and retry.")
    db.refresh(flag)
    db.add(AuditLog(
        id=str(uuid4()), flag_id=flag.id, flag_key=flag.key, action="targeting",
        actor=user.subject, before_json=json.dumps(before),
        after_json=json.dumps({**configuration(flag), "targeting": request.rules.model_dump()}),
    ))
    db.commit()
    invalidate_flag(flag.key, flag.environment)
    return flag


class GuardConfig(BaseModel):
    enabled: bool = False
    max_error_rate: float = Field(default=0.05, ge=0.001, le=0.5)
    max_p95_ms: int = Field(default=1000, ge=10, le=60000)
    min_samples: int = Field(default=20, ge=10, le=10000)
    window_seconds: int = Field(default=60, ge=30, le=3600)
    consecutive_windows: int = Field(default=2, ge=2, le=6)


@router.put("/flags/{flag_id}/guardrail")
def configure_guardrail(
    flag_id: str, request: GuardConfig,
    db: Session = Depends(get_db), user: Principal = Depends(admin),
):
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(404, "Flag not found")
    policy = db.get(GuardPolicy, flag_id)
    before = {key: getattr(policy, key) for key in GuardConfig.model_fields} if policy else {}
    if policy is None:
        policy = GuardPolicy(flag_id=flag_id, **request.model_dump())
        db.add(policy)
    else:
        for key, value in request.model_dump().items():
            setattr(policy, key, value)
    db.add(AuditLog(
        id=str(uuid4()), flag_id=flag_id, flag_key=flag.key, action="guardrail",
        actor=user.subject, before_json=json.dumps(before), after_json=request.model_dump_json(),
    ))
    db.commit()
    return {"flag_id": flag_id, **request.model_dump()}


class HealthReport(BaseModel):
    error: bool
    latency_ms: int = Field(ge=0, le=120000)


@router.post("/flags/{flag_id}/health", status_code=201)
def record_feature_health(
    flag_id: str, report: HealthReport,
    db: Session = Depends(get_db), _user: Principal = Depends(admin),
):
    if db.get(Flag, flag_id) is None:
        raise HTTPException(404, "Flag not found")
    db.add(FeatureHealthSample(id=str(uuid4()), flag_id=flag_id,
                               error=report.error, latency_ms=report.latency_ms))
    db.commit()
    return {"recorded": True, "source": "authenticated_admin_report"}


@router.post("/guardrails/check")
def run_guardrail_check(db: Session = Depends(get_db), _user: Principal = Depends(admin)):
    return {"rolled_back": evaluate_guardrails(db)}


@router.get("/dead-letters")
def list_dead_letters(
    db: Session = Depends(get_db), _user: Principal = Depends(admin),
):
    rows = db.scalars(select(DeadLetterEvent).where(DeadLetterEvent.replayed_at.is_(None))
                      .order_by(DeadLetterEvent.failed_at.desc()).limit(100)).all()
    return [
        {"id": row.id, "topic": row.topic, "partition": row.partition,
         "offset": row.offset, "reason": row.reason, "failed_at": row.failed_at.isoformat()}
        for row in rows
    ]


class ReplayRequest(BaseModel):
    type: str = Field(pattern=r"^(exposure|conversion)$")
    flag_id: str
    user_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    served: bool | None = None


@router.post("/dead-letters/{dead_letter_id}/replay", status_code=201)
def replay_dead_letter(
    dead_letter_id: str, request: ReplayRequest,
    db: Session = Depends(get_db), user: Principal = Depends(admin),
):
    row = db.get(DeadLetterEvent, dead_letter_id)
    if row is None:
        raise HTTPException(404, "Dead-letter event not found")
    if row.replayed_at is not None:
        raise HTTPException(409, "Already replayed")
    if db.get(Flag, request.flag_id) is None:
        raise HTTPException(422, "Unknown flag")
    event_id = str(uuid4())
    envelope = validate_event({"event_id": event_id, **request.model_dump()})
    result = db.execute(
        update(DeadLetterEvent).where(DeadLetterEvent.id == dead_letter_id, DeadLetterEvent.replayed_at.is_(None))
        .values(replayed_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Replay was already requested")
    db.add(EventOutbox(id=event_id, topic=os.getenv("KAFKA_TOPIC", "launchpilot.events.v1"),
                       payload_json=json.dumps(envelope)))
    db.add(AuditLog(
        id=str(uuid4()), flag_id=request.flag_id,
        flag_key=db.get(Flag, request.flag_id).key,
        action="dlq_replay", actor=user.subject,
        before_json=json.dumps({"dead_letter_id": row.id, "reason": row.reason}),
        after_json=json.dumps({"new_event_id": event_id}),
    ))
    db.commit()
    return {"queued": True, "event_id": event_id}
