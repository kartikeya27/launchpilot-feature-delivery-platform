"""Opt-in SLO guardrails driven by authenticated, persisted feature health reports.

Two or more completed, consecutive windows must breach configured thresholds;
empty / under-sampled windows NEVER trigger rollback. No external traffic required.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .cache import invalidate_flag
from .db import SessionLocal
from .models import AuditLog, FeatureHealthSample, Flag, GuardPolicy

log = logging.getLogger(__name__)


def window_statistics(samples: list[FeatureHealthSample]) -> dict:
    n = len(samples)
    if not n:
        return {"samples": 0, "error_rate": 0.0, "p95_ms": 0}
    latencies = sorted(s.latency_ms for s in samples)
    return {
        "samples": n,
        "error_rate": sum(int(s.error) for s in samples) / n,
        "p95_ms": latencies[ceil(0.95 * n) - 1],
    }


def evaluate_guardrails(db: Session, now: datetime | None = None) -> list[str]:
    """Evaluate all opted-in policies and atomically disable unhealthy flags."""
    now = now or datetime.now(timezone.utc)
    rolled_back = []
    policies = db.scalars(select(GuardPolicy).where(GuardPolicy.enabled.is_(True))).all()
    for policy in policies:
        flag = db.get(Flag, policy.flag_id)
        if flag is None or not flag.enabled:
            continue
        end_epoch = int(now.timestamp()) // policy.window_seconds * policy.window_seconds
        failures = []
        for index in range(policy.consecutive_windows):
            end = datetime.fromtimestamp(end_epoch - index * policy.window_seconds, timezone.utc)
            begin = end - timedelta(seconds=policy.window_seconds)
            samples = db.scalars(select(FeatureHealthSample).where(
                FeatureHealthSample.flag_id == flag.id,
                FeatureHealthSample.created_at >= begin,
                FeatureHealthSample.created_at < end,
            )).all()
            observed = window_statistics(samples)
            if observed["samples"] < policy.min_samples:
                failures = []
                break
            if observed["error_rate"] <= policy.max_error_rate and observed["p95_ms"] <= policy.max_p95_ms:
                failures = []
                break
            failures.append(observed)
        if len(failures) != policy.consecutive_windows:
            continue
        before = {"enabled": flag.enabled, "rollout": flag.rollout, "version": flag.version}
        result = db.execute(update(Flag).where(Flag.id == flag.id, Flag.version == flag.version, Flag.enabled.is_(True))
                            .values(enabled=False, rollout=0, version=Flag.version + 1, updated_at=now))
        if result.rowcount != 1:
            db.rollback()
            continue
        db.refresh(flag)
        db.add(AuditLog(
            id=str(uuid4()), flag_id=flag.id, flag_key=flag.key,
            action="auto_rollback", actor="slo-guardrail",
            before_json=json.dumps(before),
            after_json=json.dumps({
                "enabled": False, "rollout": 0, "version": flag.version,
                "reason": "Consecutive SLO window breaches",
                "evidence": failures,
            }),
        ))
        db.commit()
        invalidate_flag(flag.key, flag.environment)
        log.warning("SLO auto-rollback applied to %s (%s)", flag.key, flag.environment)
        rolled_back.append(flag.key)
    return rolled_back


def run_forever():
    if os.getenv("GUARDRAIL_WORKER_ENABLED") != "true":
        raise SystemExit("Guardrail worker disabled; set GUARDRAIL_WORKER_ENABLED=true")
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with SessionLocal() as db:
                evaluate_guardrails(db)
        except Exception:
            log.exception("Guardrail polling failed; no destructive fallback")
        time.sleep(max(5, int(os.getenv("GUARDRAIL_POLL_SECONDS", "15"))))


if __name__ == "__main__":
    run_forever()
