"""Release operations: environment isolation, RBAC, version conflicts and audit."""
from fastapi import HTTPException
from app import auth, main


def test_operations_read_is_environment_scoped_and_queue_counts_are_labeled_global(client):
    client.post("/api/flags", json={"key": "checkout_ops", "name": "Checkout Ops", "environment": "staging", "enabled": True, "rollout": 25})
    result = client.get("/api/operations/overview?environment=staging")
    assert result.status_code == 200
    body = result.json()
    assert body["environment"] == "staging"
    assert any(f["key"] == "checkout_ops" and f["rollout"] == 25 for f in body["flags"])
    assert body["pipeline"]["scope"] == "global"
    assert body["pipeline"]["broker_health"] == "not_measured"
    assert client.get("/api/operations/overview?environment=production").json()["flags"] == []
    assert client.get("/api/operations/overview?environment=not-an-environment").status_code == 422


def test_rollback_is_atomic_audited_and_denies_stale_versions(client):
    created = client.post("/api/flags", json={"key": "rollback_ops", "name": "Rollback Ops", "environment": "staging", "enabled": True, "rollout": 75}).json()
    rollback = client.post(
        f"/api/operations/flags/{created['id']}/rollback",
        json={"version": 1, "reason": "Elevated checkout error rate"},
    )
    assert rollback.status_code == 200
    body = rollback.json()
    assert body["enabled"] is False and body["rollout"] == 0 and body["version"] == 2
    audit = client.get("/api/audit").json()[0]
    assert audit["action"] == "rollback"
    assert audit["actor"] == "local-demo-admin"
    assert audit["after"]["reason"] == "Elevated checkout error rate"
    assert client.post("/api/evaluate", json={"key": "rollback_ops", "environment": "staging", "user_id": "synthetic-user"}).json()["enabled"] is False
    assert client.post(f"/api/operations/flags/{created['id']}/rollback", json={"version": 1, "reason": "stale write"}).status_code == 409
    assert client.post("/api/operations/flags/missing/rollback", json={"version": 1, "reason": "missing flag"}).status_code == 404
    assert client.post(f"/api/operations/flags/{created['id']}/rollback", json={"version": 2, "reason": ""}).status_code == 422


def test_viewer_can_read_operations_but_cannot_rollback(client):
    flag = client.post("/api/flags", json={"key": "viewer_ops", "name": "Viewer Ops"}).json()
    main.app.dependency_overrides[auth.admin] = lambda: (_ for _ in ()).throw(HTTPException(403, "Insufficient permissions"))
    try:
        assert client.get("/api/operations/overview").status_code == 200
        assert client.post(f"/api/operations/flags/{flag['id']}/rollback", json={"version": 1, "reason": "Not authorized"}).status_code == 403
    finally:
        main.app.dependency_overrides.clear()
