import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import decode_access_token
from app.cache import get_cached_flag, set_cached_flag, invalidate_flag
from app.statistics import compare, wilson
from app.db import SessionLocal
from app.models import EventOutbox


def test_statistics_balanced_and_warning():
    result = compare(50, 500, 75, 500)
    assert result["absolute_lift"] == 0.05
    assert result["p_value"] < 0.05
    assert "not randomized" in " ".join(result["warnings"])
    assert wilson(0, 0) == (0.0, 0.0)
    assert compare(0, 0, 1, 2)["p_value"] is None


def test_experiment_exposed_cohorts(client):
    client.post("/api/flags", json={"key": "exp_test", "name": "Experiment", "enabled": True, "rollout": 50})
    for i in range(200):
        user = f"person-{i}"
        r = client.post("/api/evaluate", json={"key": "exp_test", "user_id": user}).json()
        if r["enabled"] and i % 3 == 0:
            client.post("/api/events/conversion", json={"key": "exp_test", "user_id": user})
    report = client.get("/api/experiments/exp_test").json()
    assert report["control"]["users"] + report["treatment"]["users"] == 200
    assert report["treatment"]["conversions"] > 0


def test_fake_redis_cache_roundtrip():
    class FakeRedis:
        store = {}
        def get(self, key): return self.store.get(key)
        def setex(self, key, ttl, val): self.store[key] = val
        def delete(self, key): self.store.pop(key, None)
    from app import cache
    with patch.object(cache, "client", return_value=FakeRedis()):
        flag = SimpleNamespace(id="f", key="k", salt="s", environment="production", enabled=True, rollout=5, version=3)
        set_cached_flag(flag)
        assert get_cached_flag("k", "production").version == 3
        invalidate_flag("k", "production")
        assert get_cached_flag("k", "production") is None


def test_oidc_validates_signature_audience_and_expiry(monkeypatch):
    from app import auth
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    class FakeJWK:
        key = public
    class FakeClient:
        def get_signing_key_from_jwt(self, token): return FakeJWK()
    monkeypatch.setattr(auth, "jwks_client", lambda: FakeClient())
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example/realms/launchpilot")
    monkeypatch.setenv("OIDC_AUDIENCE", "launchpilot-api")
    now = datetime.now(timezone.utc)
    payload = {"iss": "https://identity.example/realms/launchpilot", "aud": "launchpilot-api", "sub": "alice", "exp": now+timedelta(minutes=5), "realm_access": {"roles": ["launchpilot_viewer"]}}
    token = jwt.encode(payload, private, algorithm="RS256", headers={"kid": "test"})
    user = decode_access_token(token)
    assert user.subject == "alice" and user.roles == frozenset({"launchpilot_viewer"})
    with pytest.raises(Exception):
        decode_access_token(jwt.encode({**payload, "aud": "wrong"}, private, algorithm="RS256"))
    with pytest.raises(Exception):
        decode_access_token(jwt.encode({**payload, "exp": now-timedelta(minutes=5)}, private, algorithm="RS256"))


def test_rbac_is_enforced_by_api(client):
    from fastapi import HTTPException
    from app import main, auth
    # Override claims server-side to test viewer denial of all admin writes.
    main.app.dependency_overrides[auth.admin] = lambda: (_ for _ in ()).throw(HTTPException(403, "Insufficient permissions"))
    try:
        assert client.get("/api/flags").status_code == 200
        assert client.post("/api/flags", json={"key": "denied", "name": "Denied"}).status_code == 403
        assert client.post("/api/demo/simulate").status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_outbox_transaction(client, monkeypatch):
    monkeypatch.setenv("EVENT_TRANSPORT", "kafka")
    client.post("/api/flags", json={"key": "async_feature", "name": "Async", "enabled": True, "rollout": 100})
    client.post("/api/evaluate", json={"key": "async_feature", "user_id": "u"})
    client.post("/api/events/conversion", json={"key": "async_feature", "user_id": "u"})
    with SessionLocal() as db:
        entries = db.query(EventOutbox).all()
        assert {json.loads(e.payload_json)["type"] for e in entries} == {"exposure", "conversion"}
        assert all("user_id" not in e.payload_json for e in entries)
    assert client.get("/api/events/pipeline").json()["pending"] == 2


def test_production_mode_cannot_use_demo_auth(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "demo")
    with pytest.raises(RuntimeError, match="requires AUTH_MODE=oidc"):
        with TestClient(app):
            pass


def test_metric_endpoint_requires_internal_bearer_token(client, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-local-token")
    assert client.get("/internal/metrics").status_code == 403
    ok = client.get("/internal/metrics", headers={"Authorization": "Bearer test-local-token"})
    assert ok.status_code == 200
    assert "launchpilot_http_requests_total" in ok.text
