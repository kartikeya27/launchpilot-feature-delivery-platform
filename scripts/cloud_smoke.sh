#!/usr/bin/env bash
# Run ONLY after an authorized GCP deployment and successful migration.
# Required: public HTTPS Cloud Run URL, actual external OIDC issuer and valid operator identity.
set -euo pipefail
BASE_URL="${1:-}"
if [[ ! "$BASE_URL" =~ ^https://[^/]+$ ]]; then
  echo "Usage: bash scripts/cloud_smoke.sh https://your-cloud-run-url" >&2
  exit 2
fi
echo "Read-only smoke checks for $BASE_URL"
curl --fail --silent --show-error --max-time 20 "$BASE_URL/api/health" | python3 -m json.tool
curl --fail --silent --show-error --max-time 20 "$BASE_URL/api/health/ready" | python3 -m json.tool
status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 20 "$BASE_URL/api/flags")
if [[ "$status" != "401" && "$status" != "403" ]]; then
  echo "FAIL: unauthenticated flags request returned HTTP $status (expected 401/403)" >&2
  exit 1
fi
echo "PASS: HTTPS health, DB readiness and unauthenticated access denial"
echo "Not tested by this script: deployment security posture, IAM, persistence, Kafka, Redis, real OIDC login."
