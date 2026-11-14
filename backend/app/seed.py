import secrets
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Flag, AuditLog

SEED = [
    ("ai_search", "AI-powered search", "Semantic search with context-aware ranking across your product.", "production", True, 35, "Search Platform"),
    ("checkout_v2", "Next-gen checkout", "A faster, simplified checkout journey with fewer steps.", "production", True, 75, "Commerce"),
    ("realtime_collab", "Real-time collaboration", "Live collaborative editing with instant presence indicators.", "production", False, 0, "Core Experience"),
    ("smart_recommendations", "Smart recommendations", "Contextual product suggestions powered by ranking models.", "production", True, 15, "ML Platform"),
    ("new_navigation", "Redesigned navigation", "Next-generation navigation experiment for internal validation.", "staging", True, 100, "Design Systems"),
]

def seed_if_empty(db: Session):
    if db.scalar(select(Flag.id).limit(1)):
        return
    for key, name, description, env, enabled, rollout, owner in SEED:
        flag = Flag(id=str(uuid4()), key=key, name=name, description=description, environment=env, enabled=enabled, rollout=rollout, owner=owner, salt=secrets.token_hex(16))
        db.add(flag)
        db.add(AuditLog(id=str(uuid4()), flag_id=flag.id, flag_key=key, action="seed", actor="demo-seeder"))
    db.commit()
