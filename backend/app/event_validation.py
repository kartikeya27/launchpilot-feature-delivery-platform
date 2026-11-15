"""Validate the restricted Kafka envelope before receipt or manual replay."""
import json
import re
from uuid import UUID


def validate_event(body: bytes | str | dict) -> dict:
    if isinstance(body, (str, bytes)):
        if len(body) > 8192:
            raise ValueError("Event exceeds 8 KiB limit")
        body = json.loads(body)
    if not isinstance(body, dict):
        raise ValueError("Event must be an object")
    if set(body) != {"event_id", "type", "flag_id", "user_hash", "served"}:
        raise ValueError("Event fields do not match the supported envelope")
    for key in ("event_id", "flag_id"):
        UUID(str(body[key]))
    if body["type"] not in ("exposure", "conversion"):
        raise ValueError("Unknown event type")
    if not isinstance(body["user_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", body["user_hash"]):
        raise ValueError("Invalid pseudonymous identity hash")
    if body["served"] is not None and not isinstance(body["served"], bool):
        raise ValueError("Invalid served value")
    return body
