#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Deployment script executed on the EC2 host (manually or by GitHub
# Actions over SSH). Pulls latest code, rebuilds containers, verifies.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/guardian-ai-news-assistant}"
COMPOSE_PROFILE="${COMPOSE_PROFILE:-prod}"

cd "$APP_DIR"

echo "==> Pulling latest code"
git fetch origin main
git reset --hard origin/main

echo "==> Rebuilding and restarting containers"
docker compose --profile "$COMPOSE_PROFILE" up -d --build

echo "==> Pruning dangling images"
docker image prune -f

echo "==> Waiting for backend to become healthy"
bash scripts/health-check.sh "http://localhost:8000" 12 5

echo "==> Deployed successfully"
docker compose ps
