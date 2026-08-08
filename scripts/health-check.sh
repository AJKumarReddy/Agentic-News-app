#!/usr/bin/env bash
# Usage: health-check.sh [base_url] [attempts] [delay_seconds]
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
ATTEMPTS="${2:-10}"
DELAY="${3:-5}"

for i in $(seq 1 "$ATTEMPTS"); do
  status=$(curl -s -o /tmp/health.json -w "%{http_code}" "$BASE_URL/api/health" || true)
  if [ "$status" = "200" ]; then
    body=$(cat /tmp/health.json)
    echo "Health check OK: $body"
    if echo "$body" | grep -q '"status": *"healthy"'; then
      exit 0
    fi
    echo "Service degraded — check component statuses above."
    exit 1
  fi
  echo "Attempt $i/$ATTEMPTS: backend not ready yet (HTTP $status). Retrying in ${DELAY}s…"
  sleep "$DELAY"
done

echo "Health check FAILED after $ATTEMPTS attempts."
exit 1
