#!/usr/bin/env bash
# Dedicated, disposable GitHub Actions environment ONLY. Never run against real data.
set -euo pipefail
COMPOSE=(docker compose -f compose.production.yaml)

TOPIC="launchpilot.events.v1"
KAFKA_TOPICS="/opt/kafka/bin/kafka-topics.sh"

topic_ready() {
  "${COMPOSE[@]}" exec -T kafka "$KAFKA_TOPICS" --bootstrap-server localhost:9092 \
    --describe --topic "$TOPIC" 2>/dev/null | grep -q "Topic: $TOPIC"
}

echo "Ensuring the event topic exists and the broker is ready before the outage"
topic_created=false
for i in $(seq 1 45); do
  if "${COMPOSE[@]}" exec -T kafka "$KAFKA_TOPICS" --bootstrap-server localhost:9092 \
    --create --if-not-exists --topic "$TOPIC" --partitions 1 --replication-factor 1 >/dev/null 2>&1; then
    topic_created=true
    break
  fi
  sleep 2
done
if [ "$topic_created" != true ]; then
  echo "FAIL: Kafka did not accept topic creation before outage"
  exit 1
fi
if ! topic_ready; then
  echo "FAIL: topic was not visible before the outage"
  exit 1
fi


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

echo "Restarting Kafka and checking broker/topic readiness"
"${COMPOSE[@]}" start kafka
broker_ready=false
for i in $(seq 1 60); do
  if topic_ready; then
    broker_ready=true
    break
  fi
  sleep 2
done
if [ "$broker_ready" != true ]; then
  echo "FAIL: Kafka topic did not recover"
  "${COMPOSE[@]}" logs --tail=100 kafka
  exit 1
fi

echo "Broker recovered. Waiting for automatic outbox publishing and consumption"
for i in $(seq 1 120); do
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
echo "Outbox publish state and matching receipts:"
"${COMPOSE[@]}" exec -T postgres psql -U launchpilot -d launchpilot -c \
  "SELECT id, published_at FROM event_outbox WHERE id='$EVENT_ID';"
"${COMPOSE[@]}" exec -T postgres psql -U launchpilot -d launchpilot -c \
  "SELECT event_id, ingested_at FROM event_receipts WHERE event_id='$EVENT_ID';"
"${COMPOSE[@]}" ps kafka publisher consumer
"${COMPOSE[@]}" logs --tail=100 publisher consumer kafka
exit 1
