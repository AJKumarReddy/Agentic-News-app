#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# One-time setup for a fresh Ubuntu 22.04/24.04 EC2 instance.
# Run as the default 'ubuntu' user:  bash setup-ec2.sh
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "==> Updating system packages"
sudo apt update && sudo apt upgrade -y

echo "==> Installing git, nginx tooling prerequisites, certbot"
sudo apt install -y git ca-certificates curl gnupg certbot

echo "==> Installing Docker Engine + Compose plugin"
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> Allowing the current user to run docker without sudo"
sudo usermod -aG docker "$USER"

echo "==> Cloning the repository (edit REPO_URL first if needed)"
REPO_URL="${REPO_URL:-}"
APP_DIR="$HOME/guardian-ai-news-assistant"
if [ -n "$REPO_URL" ] && [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

echo
echo "──────────────────────────────────────────────────────────────"
echo " Next steps:"
echo "  1. Log out and back in (docker group membership)."
echo "  2. cd $APP_DIR && cp .env.example .env && nano .env"
echo "     Set: ENVIRONMENT=production, real API keys, a strong"
echo "     POSTGRES_PASSWORD, FRONTEND_URL=https://mydomain.com,"
echo "     VITE_API_BASE_URL=https://api.mydomain.com/api"
echo "  3. Edit nginx/nginx.conf → replace mydomain.com."
echo "  4. Issue certificates (nginx not running yet):"
echo "       sudo certbot certonly --standalone -d api.mydomain.com"
echo "  5. docker compose --profile prod up -d --build"
echo "  6. bash scripts/health-check.sh http://localhost:8000"
echo "──────────────────────────────────────────────────────────────"
