import json
import os
import random
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Principal, admin, principal, viewer
from .cache import get_cached_flag, invalidate_flag, set_cached_flag
from .events import enqueue
from .statistics import compare
from .telemetry import CACHE, EVENTS, instrument, metrics_middleware, metrics_response
from .core import evaluate, user_fingerprint
from .db import Base, SessionLocal, engine, get_db
from .models import AuditLog, Conversion, Exposure, Flag, EventOutbox, EventReceipt
from .schemas import ConversionRequest, EvalRequest, EvalResponse, FlagCreate, FlagOut, FlagUpdate
from .seed import seed_if_empty

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("APP_ENV", "development") == "production" and os.getenv("AUTH_MODE", "demo") != "oidc":
        raise RuntimeError("Production requires AUTH_MODE=oidc")
    if os.getenv("AUTH_MODE", "demo") == "oidc" and not all(os.getenv(k) for k in ("OIDC_ISSUER", "OIDC_AUDIENCE")):
        raise RuntimeError("OIDC_ISSUER and OIDC_AUDIENCE must be set")
    if os.getenv("APP_ENV", "development") != "production" and os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true":
        Base.metadata.create_all(bind=engine)
    if os.getenv("SEED_DEMO", "true").lower() == "true":
        with SessionLocal() as session:
            seed_if_empty(session)
    yield

app = FastAPI(title="LaunchPilot API", version="1.0.0", description="Progressive delivery control plane demo", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","), allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "Authorization"])
app.middleware("http")(metrics_middleware)
instrument(app)

def snapshot(flag: Flag):
    return {"enabled": flag.enabled, "rollout": flag.rollout, "name": flag.name, "owner": flag.owner, "description": flag.description, "version": flag.version}

def audit(db: Session, flag: Flag, action: str, before: dict | None, after: dict | None, actor="local-demo-admin"):
    db.add(AuditLog(id=str(uuid4()), flag_id=flag.id, flag_key=flag.key, action=action, actor=actor, before_json=json.dumps(before or {}), after_json=json.dumps(after or {})))

def get_flag(db: Session, key: str, environment: str) -> Flag:
    flag = db.scalar(select(Flag).where(Flag.key == key, Flag.environment == environment))
    if not flag:
        raise HTTPException(404, detail="Flag not found")
    return flag

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "launchpilot-api", "mode": os.getenv("AUTH_MODE", "demo")}

@app.get("/api/me")
def me(user: Principal = Depends(principal)):
    return {"subject": user.subject, "roles": sorted(user.roles)}

@app.get("/internal/metrics")
def internal_metrics(authorization: str = Header(default="")):
    # Never expose on public ingress. Additional shared token for local Prometheus scraping.
    required = os.getenv("METRICS_TOKEN", "")
    if not required or not secrets.compare_digest(authorization, f"Bearer {required}"):
        raise HTTPException(403, detail="Internal metrics unavailable")
    return metrics_response()

@app.get("/api/health/ready")
def readiness(db: Session = Depends(get_db)):
    db.execute(select(1)).scalar_one()
    return {"status": "ready"}

@app.get("/api/flags", response_model=list[FlagOut])
def list_flags(environment: str | None = Query(default=None), db: Session = Depends(get_db), user: Principal = Depends(viewer)):
    query = select(Flag).order_by(Flag.created_at)
    if environment:
        if environment not in {"production", "staging", "development"}:
            raise HTTPException(422, detail="Invalid environment")
        query = query.where(Flag.environment == environment)
    return db.scalars(query).all()

@app.post("/api/flags", response_model=FlagOut, status_code=201)
def create_flag(payload: FlagCreate, db: Session = Depends(get_db), user: Principal = Depends(admin)):
    flag = Flag(id=str(uuid4()), salt=secrets.token_hex(16), **payload.model_dump())
    db.add(flag)
    audit(db, flag, "created", None, snapshot(flag), actor=user.subject)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="A flag with this key already exists in this environment") from None
    db.refresh(flag)
    invalidate_flag(flag.key, flag.environment)
    return flag

@app.put("/api/flags/{flag_id}", response_model=FlagOut)
def update_flag(flag_id: str, payload: FlagUpdate, db: Session = Depends(get_db), user: Principal = Depends(admin)):
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(404, detail="Flag not found")
    if flag.version != payload.version:
        raise HTTPException(409, detail="Flag was modified by another user. Refresh and try again.")
    before = snapshot(flag)
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True, exclude={"version"}).items() if v is not None}
    # Compare-and-swap is atomic in PostgreSQL across multiple API replicas.
    result = db.execute(
        update(Flag).where(Flag.id == flag_id, Flag.version == payload.version).values(
            **fields, version=Flag.version + 1, updated_at=datetime.now(timezone.utc)
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, detail="Flag was concurrently modified. Refresh and try again.")
    db.refresh(flag)
    audit(db, flag, "updated", before, snapshot(flag), actor=user.subject)
    db.commit()
    invalidate_flag(flag.key, flag.environment)
    return flag

@app.post("/api/evaluate", response_model=EvalResponse)
def evaluate_flag(payload: EvalRequest, db: Session = Depends(get_db), user: Principal = Depends(viewer)):
    flag = get_cached_flag(payload.key, payload.environment)
    if flag is not None:
        CACHE.labels("hit").inc()
    else:
        CACHE.labels("miss").inc()
        flag = get_flag(db, payload.key, payload.environment)
        set_cached_flag(flag)
    served, reason, bucket = evaluate(flag, payload.user_id)
    if payload.track:
        # FK-valid row required for tracking; cached config is read-only and short-lived.
        flag_row = get_flag(db, payload.key, payload.environment)
        if flag_row.version != flag.version:
            flag = flag_row
            served, reason, bucket = evaluate(flag, payload.user_id)
            set_cached_flag(flag)
        fingerprint = user_fingerprint(flag, payload.user_id)
        db.add(Exposure(id=str(uuid4()), flag_id=flag.id, user_hash=fingerprint, served=served))
        enqueue(db, "exposure", flag.id, fingerprint, served)
        db.commit()
        EVENTS.labels("exposure").inc()
    return EvalResponse(key=flag.key, environment=flag.environment, enabled=served, reason=reason, bucket=bucket, rollout=flag.rollout, flag_version=flag.version)

@app.post("/api/events/conversion", status_code=201)
def track_conversion(payload: ConversionRequest, db: Session = Depends(get_db), user: Principal = Depends(viewer)):
    flag = get_flag(db, payload.key, payload.environment)
    hashed = user_fingerprint(flag, payload.user_id)
    # Only count conversions by exposed users; repeat conversions are deduplicated.
    exposed = db.scalar(select(Exposure.id).where(Exposure.flag_id == flag.id, Exposure.user_hash == hashed).limit(1))
    if not exposed:
        raise HTTPException(400, detail="Evaluate this flag for the user before recording a conversion")
    exists = db.scalar(select(Conversion.id).where(Conversion.flag_id == flag.id, Conversion.user_hash == hashed))
    if exists:
        return {"recorded": False, "reason": "duplicate"}
    db.add(Conversion(id=str(uuid4()), flag_id=flag.id, user_hash=hashed))
    enqueue(db, "conversion", flag.id, hashed)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"recorded": False, "reason": "duplicate"}
    EVENTS.labels("conversion").inc()
    return {"recorded": True}

@app.get("/api/analytics")
def analytics(environment: str = "production", db: Session = Depends(get_db), user: Principal = Depends(viewer)):
    if environment not in {"production", "staging", "development"}:
        raise HTTPException(422, detail="Invalid environment")
    flags = db.scalars(select(Flag).where(Flag.environment == environment)).all()
    ids = [f.id for f in flags]
    today = datetime.now(timezone.utc).date()
    labels = [(today - timedelta(days=d)).isoformat() for d in range(6, -1, -1)]
    if not ids:
        return {"total_flags": 0, "active_flags": 0, "evaluations": 0, "unique_users": 0, "conversions": 0, "conversion_rate": 0, "daily": [{"date": x, "evaluations": 0, "conversions": 0} for x in labels], "flags": []}
    since = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
    exposures = db.scalars(select(Exposure).where(Exposure.flag_id.in_(ids), Exposure.created_at >= since)).all()
    conversions = db.scalars(select(Conversion).where(Conversion.flag_id.in_(ids), Conversion.created_at >= since)).all()
    by_flag = Counter(x.flag_id for x in exposures)
    conv_by_flag = Counter(x.flag_id for x in conversions)
    daily_exp = Counter(x.created_at.date().isoformat() for x in exposures)
    daily_conv = Counter(x.created_at.date().isoformat() for x in conversions)
    # Conversion rate is unique converted subjects / unique exposed subjects, not evaluations.
    distinct = {(x.flag_id, x.user_hash) for x in exposures}
    return {
        "total_flags": len(flags), "active_flags": sum(bool(f.enabled) for f in flags),
        "evaluations": len(exposures), "unique_users": len(distinct), "conversions": len(conversions),
        "conversion_rate": round(len(conversions) / len(distinct) * 100, 1) if distinct else 0,
        "daily": [{"date": day, "evaluations": daily_exp[day], "conversions": daily_conv[day]} for day in labels],
        "flags": [{"id": f.id, "key": f.key, "evaluations": by_flag[f.id], "conversions": conv_by_flag[f.id]} for f in flags],
    }

@app.get("/api/audit")
def audit_history(limit: int = Query(default=30, ge=1, le=100), db: Session = Depends(get_db), user: Principal = Depends(viewer)):
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [{"id": log.id, "flag_key": log.flag_key, "action": log.action, "actor": log.actor, "before": json.loads(log.before_json), "after": json.loads(log.after_json), "created_at": log.created_at.isoformat()} for log in logs]

@app.post("/api/demo/simulate")
def simulate_traffic(environment: str = "production", count: int = Query(default=250, ge=1, le=1000), db: Session = Depends(get_db), user: Principal = Depends(admin)):
    """Synthetic sample traffic: NOT real production data and not a load/performance test."""
    if environment not in {"production", "staging", "development"}:
        raise HTTPException(422, detail="Invalid environment")
    flags = db.scalars(select(Flag).where(Flag.environment == environment)).all()
    if not flags:
        return {"generated": 0, "conversions": 0, "synthetic": True}
    generated, converted = 0, 0
    unique_users = [f"synthetic-demo-user-{secrets.token_hex(6)}" for _ in range(count)]
    for user_id in unique_users:
        for flag in flags:
            served, _, _ = evaluate(flag, user_id)
            hash_id = user_fingerprint(flag, user_id)
            db.add(Exposure(id=str(uuid4()), flag_id=flag.id, user_hash=hash_id, served=served))
            generated += 1
            if served and random.random() < 0.23:
                db.add(Conversion(id=str(uuid4()), flag_id=flag.id, user_hash=hash_id))
                converted += 1
    db.commit()
    return {"generated": generated, "conversions": converted, "synthetic": True}

@app.get("/api/experiments/{flag_key}")
def experiment_results(flag_key: str, environment: str = "production", db: Session = Depends(get_db), user: Principal = Depends(viewer)):
    flag = get_flag(db, flag_key, environment)
    # Deduplicate subjects; first assignment is preserved in historical cohort.
    exposures = db.scalars(select(Exposure).where(Exposure.flag_id == flag.id).order_by(Exposure.created_at, Exposure.id)).all()
    cohorts = {}
    for exposure in exposures:
        cohorts.setdefault(exposure.user_hash, exposure.served)
    converted = set(db.scalars(select(Conversion.user_hash).where(Conversion.flag_id == flag.id)).all())
    control = {user_hash for user_hash, treated in cohorts.items() if not treated}
    treatment = {user_hash for user_hash, treated in cohorts.items() if treated}
    result = compare(len(control & converted), len(control), len(treatment & converted), len(treatment))
    return {"flag_key": flag_key, "environment": environment, "method": "two-sided pooled z-test; 95% Wilson intervals", **result}

@app.get("/api/events/pipeline")
def pipeline_status(db: Session = Depends(get_db), user: Principal = Depends(admin)):
    from sqlalchemy import func
    pending = db.scalar(select(func.count()).select_from(EventOutbox).where(EventOutbox.published_at.is_(None)))
    delivered = db.scalar(select(func.count()).select_from(EventOutbox).where(EventOutbox.published_at.is_not(None)))
    ingested = db.scalar(select(func.count()).select_from(EventReceipt))
    return {"transport": os.getenv("EVENT_TRANSPORT", "disabled"), "pending": pending, "published": delivered, "ingested": ingested}

# Multi-stage Docker builds copy a production frontend into this directory.
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
