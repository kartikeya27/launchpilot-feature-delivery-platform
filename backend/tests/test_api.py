from app.core import evaluate
from app.models import Flag


def payload(**extra):
    return {"key": "new_feature", "name": "New feature", "environment": "production", "enabled": True, "rollout": 50, **extra}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_create_list_and_audit(client):
    response = client.post("/api/flags", json=payload())
    assert response.status_code == 201
    assert len(client.get("/api/flags").json()) == 1
    audit = client.get("/api/audit").json()
    assert audit[0]["action"] == "created"
    assert audit[0]["flag_key"] == "new_feature"


def test_duplicate_key_conflict(client):
    assert client.post("/api/flags", json=payload()).status_code == 201
    assert client.post("/api/flags", json=payload()).status_code == 409


def test_same_key_different_environment(client):
    assert client.post("/api/flags", json=payload()).status_code == 201
    assert client.post("/api/flags", json=payload(environment="staging")).status_code == 201
    assert len(client.get("/api/flags?environment=staging").json()) == 1


def test_rollout_boundaries(client):
    flag = client.post("/api/flags", json=payload(rollout=0)).json()
    r = client.post("/api/evaluate", json={"key": flag["key"], "user_id": "u1"}).json()
    assert not r["enabled"] and r["reason"] == "rollout_zero"
    updated = client.put(f"/api/flags/{flag['id']}", json={"version": 1, "rollout": 100}).json()
    assert updated["version"] == 2
    assert client.post("/api/evaluate", json={"key": flag["key"], "user_id": "u1"}).json()["enabled"]


def test_disabled_flag_never_serves(client):
    client.post("/api/flags", json=payload(enabled=False, rollout=100))
    assert client.post("/api/evaluate", json={"key": "new_feature", "user_id": "abc"}).json()["reason"] == "flag_disabled"


def test_deterministic_bucket_and_no_tracking(client):
    client.post("/api/flags", json=payload())
    body = {"key": "new_feature", "user_id": "person_123", "track": False}
    first = client.post("/api/evaluate", json=body).json()
    second = client.post("/api/evaluate", json=body).json()
    assert first == second
    assert client.get("/api/analytics").json()["evaluations"] == 0


def test_conflict_on_stale_version(client):
    flag = client.post("/api/flags", json=payload()).json()
    assert client.put(f"/api/flags/{flag['id']}", json={"version": 1, "rollout": 65}).status_code == 200
    assert client.put(f"/api/flags/{flag['id']}", json={"version": 1, "rollout": 80}).status_code == 409


def test_conversions_are_deduplicated_and_require_exposure(client):
    client.post("/api/flags", json=payload(rollout=100))
    body = {"key": "new_feature", "user_id": "test-user"}
    assert client.post("/api/events/conversion", json=body).status_code == 400
    client.post("/api/evaluate", json=body)
    assert client.post("/api/events/conversion", json=body).json()["recorded"]
    assert not client.post("/api/events/conversion", json=body).json()["recorded"]
    metrics = client.get("/api/analytics").json()
    assert metrics["evaluations"] == 1
    assert metrics["conversions"] == 1
    assert metrics["conversion_rate"] == 100


def test_validation_and_404(client):
    assert client.post("/api/flags", json=payload(rollout=101)).status_code == 422
    assert client.post("/api/flags", json=payload(key="BAD KEY")).status_code == 422
    assert client.post("/api/evaluate", json={"key": "nope", "user_id": "u"}).status_code == 404


def test_synthetic_traffic_is_labelled(client):
    client.post("/api/flags", json=payload(rollout=100))
    result = client.post("/api/demo/simulate?count=5").json()
    assert result["synthetic"] is True
    assert result["generated"] == 5
    assert client.get("/api/analytics").json()["unique_users"] == 5


def test_environment_isolation(client):
    client.post("/api/flags", json=payload(environment="staging"))
    assert client.get("/api/analytics?environment=production").json()["total_flags"] == 0
    assert client.get("/api/analytics?environment=staging").json()["total_flags"] == 1


def test_rollout_distribution_sanity():
    f = Flag(id="1", salt="fixedsalt", key="search", environment="production", name="Search", enabled=True, rollout=30)
    observed = sum(evaluate(f, f"user-{i}")[0] for i in range(3000)) / 3000
    assert 0.25 < observed < 0.35
