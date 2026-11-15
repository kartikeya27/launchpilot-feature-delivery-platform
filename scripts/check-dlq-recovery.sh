#!/usr/bin/env bash
# GitHub Actions uses disposable Docker volumes; do NOT run destructive cleanup on real data.
set -euo pipefail
COMPOSE=(docker compose -f compose.production.yaml)
echo "Injecting one malformed synthetic Kafka message to validate durable DLQ handling"
printf '{"malformed":true}\n' | "${COMPOSE[@]}" exec -T kafka /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 --topic launchpilot.events.v1
for i in $(seq 1 60); do
  count=$("${COMPOSE[@]}" exec -T postgres psql -U launchpilot -d launchpilot -Atc \
    "SELECT COUNT(*) FROM event_dead_letters WHERE reason LIKE '%Event fields%'" | tr -d '[:space:]')
  if [ "$count" -ge 1 ] 2>/dev/null; then
    echo "PASS: invalid event durably quarantined rather than crashing consumer"
    exit 0
  fi
  sleep 2
done
echo "FAIL: consumer did not persist invalid Kafka record to DLQ"
"${COMPOSE[@]}" logs --tail=70 consumer kafka
exit 1
