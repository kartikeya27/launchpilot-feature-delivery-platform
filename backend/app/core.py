"""Stable rollout bucketing with privacy-preserving contextual targeting."""
import hashlib
import json

from .models import Flag


def user_fingerprint(flag: Flag, user_id: str) -> str:
    # Pseudonymous only; don't treat this as strong anonymity.
    return hashlib.sha256(f"{flag.salt}:{user_id}".encode()).hexdigest()


def stable_bucket(flag: Flag, user_id: str) -> int:
    """Deterministic bucket in [0, 9999]; never include mutable context in the hash."""
    payload = f"{flag.salt}:{flag.environment}:{flag.key}:{user_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 10000


def matches_targeting(flag: Flag, country: str | None, plan: str | None) -> bool:
    rules = json.loads(getattr(flag, "targeting_json", "{}") or "{}")
    filters = []
    if rules.get("countries"):
        filters.append(bool(country and country.upper() in rules["countries"]))
    if rules.get("plans"):
        filters.append(bool(plan and plan.lower() in rules["plans"]))
    if not filters:
        return True
    return any(filters) if rules.get("match") == "any" else all(filters)


def evaluate(flag: Flag, user_id: str, country: str | None = None, plan: str | None = None) -> tuple[bool, str, float]:
    bucket = stable_bucket(flag, user_id)
    if not flag.enabled:
        return False, "flag_disabled", bucket / 100
    if not matches_targeting(flag, country, plan):
        return False, "targeting_mismatch", bucket / 100
    if flag.rollout == 0:
        return False, "rollout_zero", bucket / 100
    if bucket < flag.rollout * 100:
        return True, "in_rollout", bucket / 100
    return False, "outside_rollout", bucket / 100
