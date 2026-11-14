"""Outbox publisher and Kafka consumer. Run in separate processes."""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4
from confluent_kafka import Consumer, Producer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import EventOutbox, EventReceipt

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("launchpilot.worker")

def kafka_config():
    conf = {"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"]}
    if os.getenv("KAFKA_SECURITY_PROTOCOL"):
        conf.update({"security.protocol": os.environ["KAFKA_SECURITY_PROTOCOL"], "sasl.mechanism": os.getenv("KAFKA_SASL_MECHANISM", "PLAIN"), "sasl.username": os.environ["KAFKA_SASL_USERNAME"], "sasl.password": os.environ["KAFKA_SASL_PASSWORD"]})
    return conf

def publish_forever():
    producer = Producer({**kafka_config(), "enable.idempotence": True, "acks": "all"})
    while True:
        with SessionLocal() as db:
            # Skip locked permits multiple workers without double-claiming a row.
            pending = db.scalars(select(EventOutbox).where(EventOutbox.published_at.is_(None)).order_by(EventOutbox.created_at).limit(100).with_for_update(skip_locked=True)).all()
            for item in pending:
                delivered = []
                producer.produce(item.topic, key=item.id, value=item.payload_json, on_delivery=lambda err, msg: delivered.append(err))
                remaining = producer.flush(10)
                if remaining or delivered != [None]:
                    log.warning("Kafka delivery deferred for %s", item.id)
                    break
                item.published_at = datetime.now(timezone.utc)
                db.commit()
        time.sleep(1)

def consume_forever():
    consumer = Consumer({**kafka_config(), "group.id": "launchpilot-ingester-v1", "auto.offset.reset": "earliest", "enable.auto.commit": False})
    consumer.subscribe([os.getenv("KAFKA_TOPIC", "launchpilot.events.v1")])
    try:
        while True:
            msg = consumer.poll(2.0)
            if msg is None:
                continue
            if msg.error():
                log.warning("Kafka consumer error: %s", msg.error())
                continue
            data = json.loads(msg.value())
            with SessionLocal() as db:
                db.add(EventReceipt(id=str(uuid4()), event_id=data["event_id"], event_type=data["type"]))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()  # duplicate delivery already ingested
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"publish", "consume"}:
        raise SystemExit("Usage: python -m app.worker [publish|consume]")
    (publish_forever if sys.argv[1] == "publish" else consume_forever)()
