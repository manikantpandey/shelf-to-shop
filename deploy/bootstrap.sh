#!/usr/bin/env bash
# First boot (called from CloudFormation user data) and safe to re-run.
# Installs Docker, writes deploy/.env from SSM Parameter Store, starts the stack.
# Usage: bootstrap.sh DOMAIN ACME_EMAIL SECRETS_PREFIX REGION
set -euo pipefail

DOMAIN="${1:?domain}"
ACME_EMAIL="${2:?acme email}"
PREFIX="${3:?secrets prefix, e.g. /shelf-to-shop/}"
REGION="${4:?aws region}"
APP_DIR=/opt/shelf

if ! command -v docker >/dev/null; then
  apt-get update
  apt-get install -y docker.io docker-compose-v2 jq unzip
  systemctl enable --now docker
fi
if ! command -v aws >/dev/null; then
  snap install aws-cli --classic
fi

# Secrets: SecureString parameters under PREFIX (e.g. /shelf-to-shop/META_API_KEY).
umask 077
ENV_FILE="$APP_DIR/deploy/.env"
{
  echo "ENVIRONMENT=demo"
  echo "DEMO_LOGIN_ENABLED=true"
  echo "PROVIDERS=meta"
  echo "SITE_HOST=$DOMAIN"
  echo "ACME_EMAIL=$ACME_EMAIL"
  echo "PUBLIC_BASE_URL=https://$DOMAIN"
  echo "CORS_ORIGINS=[\"https://$DOMAIN\"]"
  aws ssm get-parameters-by-path --region "$REGION" --path "$PREFIX" --with-decryption \
    --query 'Parameters[].[Name,Value]' --output text |
    while IFS=$'\t' read -r name value; do
      echo "${name#"$PREFIX"}=$value"
    done
} >"$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

for required in META_API_KEY SECRET_KEY POSTGRES_PASSWORD; do
  grep -q "^$required=." "$ENV_FILE" || { echo "missing $PREFIX$required in Parameter Store" >&2; exit 1; }
done

cd "$APP_DIR/deploy"
docker compose -f compose.prod.yml --env-file .env up -d --build
echo "Shelf-to-Shop is starting at https://$DOMAIN (certificate is issued once DNS points here)."
