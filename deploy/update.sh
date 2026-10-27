#!/usr/bin/env bash
# Deploy the latest code: run on the server from a Session Manager shell.
# Usage: sudo /opt/shelf/deploy/update.sh [git-ref]
set -euo pipefail
REF="${1:-main}"
cd /opt/shelf
git fetch --depth 1 origin "$REF"
git checkout --force FETCH_HEAD
cd deploy
docker compose -f compose.prod.yml --env-file .env up -d --build
docker image prune -f >/dev/null
docker compose -f compose.prod.yml ps
