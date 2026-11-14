"""Cache flag *configuration*, never user identities. Unavailable Redis falls back to DB."""
import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

@dataclass
class CachedFlag:
    id: str
    key: str
    salt: str
    environment: str
    enabled: bool
    rollout: int
    version: int

@lru_cache(maxsize=1)
def client():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    import redis
    return redis.Redis.from_url(url, socket_connect_timeout=0.25, socket_timeout=0.25)

def cache_key(key: str, environment: str) -> str:
    return f"lp:flag:{environment}:{key}"

def get_cached_flag(key: str, environment: str) -> CachedFlag | None:
    r = client()
    if r is None:
        return None
    try:
        raw = r.get(cache_key(key, environment))
        return CachedFlag(**json.loads(raw)) if raw else None
    except Exception as exc:
        logger.warning("Redis read unavailable: %s", type(exc).__name__)
        return None

def set_cached_flag(flag) -> None:
    r = client()
    if r is None:
        return
    fields = ("id", "key", "salt", "environment", "enabled", "rollout", "version")
    try:
        r.setex(cache_key(flag.key, flag.environment), int(os.getenv("CACHE_TTL_SECONDS", "15")), json.dumps({x: getattr(flag, x) for x in fields}))
    except Exception as exc:
        logger.warning("Redis write unavailable: %s", type(exc).__name__)

def invalidate_flag(key: str, environment: str) -> None:
    r = client()
    if r is None:
        return
    try:
        r.delete(cache_key(key, environment))
    except Exception as exc:
        logger.warning("Redis invalidate failed; entry expires via TTL: %s", type(exc).__name__)
