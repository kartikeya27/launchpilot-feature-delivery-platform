"""Advanced targeting, guarded rollbacks and dead-letter recovery."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import auth, main
from app.db import SessionLocal
from app.event_validation import validate_event
from app.guardrails import evaluate_guardrails
from app.models import AuditLog, DeadLetterEvent, EventOutbox, FeatureHealthSample, Flag


def test_context_targeting_is_audited_and_stable(client):
    created = client.post("/api/flags", json={
        "key": "premium_rollout", "name": "Premium Rollout", "environment": "staging",
        "enabled": True, "rollout": 100,
    }).json()
    changed = client.put(f"/api/operations/flags/{created['id']}/targeting", json={
        "version": created["version"],
        "rules": {"countries": ["us", "ca"], "plans": ["premium"], "match": "all"},
    })
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    assert client.put(f"/api/operations/flags/{created['id']}/targeting", json={
        "version": 1, "rules": {"countries": ["FR"]},
    }).status_code == 409
    assert client.put(f"/api/operations/flags/{created['id']}/targeting", json={
        "version": 2, "rules": {"countries": ["XXX"]},
    }).status_code == 422
    base = {"key": "premium_rollout", "environment": "staging", "user_id": "synthetic-user"}
    first = client.post("/api/evaluate", json={**base, "country": "us", "plan": "premium"}).json()
    again = client.post("/api/evaluate", json={**base, "country": "us", "plan": "premium"}).json()
    mismatch = client.post("/api/evaluate", json={**base, "country": "de", "plan": "free"}).json()
    absent = client.post("/api/evaluate", json=base).json()
    assert first["enabled"] is True and first["bucket"] == again["bucket"]
    assert mismatch["enabled"] is False and mismatch["reason"] == "targeting_mismatch"
    assert absent["enabled"] is False
    assert client.get("/api/audit").json()[0]["action"] == "targeting"


def test_guardrail_requires_two_completed_breaches_and_never_acts_without_samples(client):
    flag = client.post("/api/flags", json={
        "key": "guarded_release", "name": "Guarded Release", "environment": "staging",
        "enabled": True, "rollout": 70,
    }).json()
    url = f"/api/operations/flags/{flag['id']}/guardrail"
    policy = client.put(url, json={
        "enabled": True, "max_error_rate": 0.1, "max_p95_ms": 500,
        "min_samples": 10, "window_seconds": 60, "consecutive_windows": 2,
    })
    assert policy.status_code == 200
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        assert evaluate_guardrails(db, now) == []
        floor = datetime.fromtimestamp(int(now.timestamp()) // 60 * 60, timezone.utc)
        for window in (1, 2):
            when = floor - timedelta(seconds=window * 60 - 5)
            for _ in range(10):
                db.add(FeatureHealthSample(id=str(uuid4()), flag_id=flag["id"], error=True,
                                           latency_ms=900, created_at=when))
        db.commit()
        assert evaluate_guardrails(db, now) == ["guarded_release"]
        assert evaluate_guardrails(db, now) == []
        updated = db.get(Flag, flag["id"])
        assert updated.enabled is False and updated.rollout == 0 and updated.version == 2
        log = db.scalar(select(AuditLog).where(AuditLog.flag_id == flag["id"],
                                               AuditLog.action == "auto_rollback"))
        assert log is not None and log.actor == "slo-guardrail"


def test_guardrail_health_ingestion_and_disabled_default(client):
    flag = client.post("/api/flags", json={"key": "safe_rails", "name": "Safe Rails"}).json()
    endpoint = f"/api/operations/flags/{flag['id']}"
    assert client.post(endpoint + "/health", json={"error": True, "latency_ms": 300}).status_code == 201
    assert client.put(endpoint + "/guardrail", json={}).json()["enabled"] is False
    assert client.post("/api/operations/guardrails/check").json()["rolled_back"] == []
    assert client.post(endpoint + "/health", json={"error": False, "latency_ms": -1}).status_code == 422


def test_dlq_validation_replay_is_audited_and_idempotent(client):
    flag = client.post("/api/flags", json={"key": "dead_event", "name": "Dead Event"}).json()
    dead_id = str(uuid4())
    with SessionLocal() as db:
        db.add(DeadLetterEvent(id=dead_id, topic="launchpilot.events.v1",
                               partition=0, offset=567, payload_json="invalid",
                               reason="Invalid JSON"))
        db.commit()
    letters = client.get("/api/operations/dead-letters").json()
    assert any(item["id"] == dead_id for item in letters)
    request = {
        "type": "exposure", "flag_id": flag["id"],
        "user_hash": hashlib.sha256(b"synthetic").hexdigest(), "served": True,
    }
    response = client.post(f"/api/operations/dead-letters/{dead_id}/replay", json=request)
    assert response.status_code == 201
    event_id = response.json()["event_id"]
    with SessionLocal() as db:
        outbox = db.get(EventOutbox, event_id)
        assert outbox is not None
        assert validate_event(outbox.payload_json)["event_id"] == event_id
    assert client.post(f"/api/operations/dead-letters/{dead_id}/replay", json=request).status_code == 409
    assert client.get("/api/operations/dead-letters").json() == []
    assert client.get("/api/audit").json()[0]["action"] == "dlq_replay"


@pytest.mark.parametrize("payload", [b"{oops", b"{}", b"[]", b'{"type":"exposure"}'])
def test_bad_kafka_envelopes_are_rejected(payload):
    with pytest.raises((ValueError, TypeError)):
        validate_event(payload)


def test_configuration_and_dlq_are_admin_only(client):
    flag = client.post("/api/flags", json={"key": "acl_slo", "name": "ACL SLO"}).json()
    main.app.dependency_overrides[auth.admin] = lambda: (_ for _ in ()).throw(
        HTTPException(403, "Insufficient permissions")
    )
    try:
        assert client.get("/api/operations/dead-letters").status_code == 403
        assert client.put(f"/api/operations/flags/{flag['id']}/guardrail", json={}).status_code == 403
        assert client.put(f"/api/operations/flags/{flag['id']}/targeting", json={
            "version": 1, "rules": {},
        }).status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_outbox_publish_requires_acknowledged_delivery():
    """No callback or a failed callback must leave the durable row pending."""
    from types import SimpleNamespace
    from app.worker import publish_one

    item = SimpleNamespace(id=str(uuid4()), topic="launchpilot.events.v1",
                           payload_json='{"synthetic":true}')

    class StubProducer:
        def __init__(self, mode):
            self.mode = mode
            self.callback = None

        def produce(self, topic, key, value, on_delivery):
            assert (topic, key, value) == (item.topic, item.id, item.payload_json)
            self.callback = on_delivery

        def flush(self, timeout):
            assert timeout > 0
            if self.mode == "no_ack":
                return 1
            self.callback(None if self.mode == "success" else Exception("broker unavailable"), None)
            return 0

    assert publish_one(StubProducer("success"), item) is True
    assert publish_one(StubProducer("delivery_error"), item) is False
    assert publish_one(StubProducer("no_ack"), item) is False
