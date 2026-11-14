"""Transactional outbox. Worker publishes at least once; receipt consumer dedupes by event id."""
import json
import os
from uuid import uuid4
from .models import EventOutbox

def enqueue(db, event_type: str, flag_id: str, user_hash: str, served: bool | None = None):
    if os.getenv("EVENT_TRANSPORT", "disabled") != "kafka":
        return
    event_id = str(uuid4())
    body = {"event_id": event_id, "type": event_type, "flag_id": flag_id, "user_hash": user_hash, "served": served}
    db.add(EventOutbox(id=event_id, topic=os.getenv("KAFKA_TOPIC", "launchpilot.events.v1"), payload_json=json.dumps(body)))
