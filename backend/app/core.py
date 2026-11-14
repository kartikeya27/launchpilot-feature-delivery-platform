import hashlib
from .models import Flag

def user_fingerprint(flag: Flag, user_id: str) -> str:
    # Do not persist raw user identifiers. This is a demo pseudonym, not strong anonymization.
    return hashlib.sha256(f"{flag.salt}:{user_id}".encode()).hexdigest()

def stable_bucket(flag: Flag, user_id: str) -> int:
    """Deterministic bucket in [0, 9999] for reproducible progressive rollout."""
    payload = f"{flag.salt}:{flag.environment}:{flag.key}:{user_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 10000

def evaluate(flag: Flag, user_id: str) -> tuple[bool, str, float]:
    bucket = stable_bucket(flag, user_id)
    if not flag.enabled:
        return False, "flag_disabled", bucket / 100
    if flag.rollout == 0:
        return False, "rollout_zero", bucket / 100
    if bucket < flag.rollout * 100:
        return True, "in_rollout", bucket / 100
    return False, "outside_rollout", bucket / 100
