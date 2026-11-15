#!/usr/bin/env bash
# Dedicated, disposable GitHub Actions environment ONLY. Never run against real data.
set -euo pipefail
COMPOSE=(docker compose -f compose.production.yaml)

echo "Stopping Kafka to exercise transactional-outbox durability"
"${COMPOSE[@]}" stop kafka

EVENT_ID=$("${COMPOSE[@]}" exec -T api python - <<'PY'
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select
from backend.app.db import SessionLocal
from backend.app.models import EventOutbox, Flag

with SessionLocal() as db:
    flag = db.scalar(select(Flag).where(Flag.key.like("ops_e2e_%")).order_by(Flag.created_at.desc()))
    if not flag:
        raise SystemExit("No test flag created by full-stack browser flow")
    event_id = str(uuid4())
    payload = {
        "event_id": event_id, "type": "exposure", "flag_id": flag.id,
        "user_hash": hashlib.sha256(b"synthetic-outage-event").hexdigest(), "served": False,
    }
    db.add(EventOutbox(
        id=event_id, topic="launchpilot.events.v1",
        payload_json=json.dumps(payload),
    ))
    db.commit()
    print(event_id)
PY
)
test -n "$EVENT_ID"
echo "Outbox event persisted while Kafka unavailable: $EVENT_ID"

pending=$("${COMPOSE[@]}" exec -T postgres psql -U launchpilot -d launchpilot -Atc "SELECT COUNT(*) FROM event_outbox WHERE id='$EVENT_ID' AND published_at IS NULL")
test "$pending" = 1 || { echo "FAIL: event not durably pending"; exit 1; }

echo "Restarting Kafka, waiting for publisher and consumer receipt"
"${COMPOSE[@]}" start kafka
for i in $(seq 1 90); do
  # Exactly one receipt exists for the event ID after at-least-once delivery.
  received=$("${COMPOSE[@]}" exec -T postgres psql -U launchpilot -d launchpilot -Atc "SELECT COUNT(*) FROM event_receipts WHERE event_id='$EVENT_ID'")
  if [ "$received" = "1" ]; then
    published=$("${COMPOSE[@]}" exec -T postgres psql -U launchpilot -d launchpilot -Atc "SELECT COUNT(*) FROM event_outbox WHERE id='$EVENT_ID' AND published_at IS NOT NULL")
    test "$published" = 1 || { echo "FAIL: event received but outbox not marked published"; exit 1; }
    echo "PASS: outage -> durable outbox -> Kafka publish -> exactly one receipt"
    exit 0
  fi
  sleep 2
done
echo "FAIL: event not consumed after Kafka recovery"
"${COMPOSE[@]}" logs --tail=100 publisher consumer kafka
exit 1
