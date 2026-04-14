#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR="$ROOT_DIR/infra/env"

# Avoid locale issues on systems where C.UTF-8 is unavailable to perl.
export LC_ALL=C
export LANG=C

cp_if_missing() {
  local src="$1"
  local dst="$2"
  if [[ ! -f "$dst" ]]; then
    cp "$src" "$dst"
    echo "Created $dst"
  else
    echo "Keeping existing $dst"
  fi
}

rand() {
  openssl rand -hex 32
}

replace_token() {
  local file="$1"
  local token="$2"
  local value="$3"
  perl -0pi -e "s/\Q$token\E/$value/g" "$file"
}

mkdir -p "$ENV_DIR"

cp_if_missing "$ENV_DIR/ghostfolio.env.example" "$ENV_DIR/ghostfolio.env"
cp_if_missing "$ENV_DIR/ignidash.env.example" "$ENV_DIR/ignidash.env"
cp_if_missing "$ENV_DIR/orchestrator.env.example" "$ENV_DIR/orchestrator.env"

GF_DB_PASSWORD="$(rand)"
GF_REDIS_PASSWORD="$(rand)"
GF_JWT="$(rand)"
GF_ACCESS_SALT="$(rand)"
IGNI_ADMIN_KEY="$(rand)"
IGNI_AUTH_SECRET="$(rand)"
IGNI_API_SECRET="$(rand)"

replace_token "$ENV_DIR/ghostfolio.env" "__GF_ACCESS_TOKEN_SALT__" "$GF_ACCESS_SALT"
replace_token "$ENV_DIR/ghostfolio.env" "__GF_JWT_SECRET_KEY__" "$GF_JWT"
replace_token "$ENV_DIR/ghostfolio.env" "__GF_POSTGRES_PASSWORD__" "$GF_DB_PASSWORD"
replace_token "$ENV_DIR/ghostfolio.env" "__GF_REDIS_PASSWORD__" "$GF_REDIS_PASSWORD"

replace_token "$ENV_DIR/ignidash.env" "__IGNI_CONVEX_ADMIN_KEY__" "$IGNI_ADMIN_KEY"
replace_token "$ENV_DIR/ignidash.env" "__IGNI_BETTER_AUTH_SECRET__" "$IGNI_AUTH_SECRET"
replace_token "$ENV_DIR/ignidash.env" "__IGNI_CONVEX_API_SECRET__" "$IGNI_API_SECRET"

echo ""
echo "Environment files are ready."
echo "Next:"
echo "  1) Open $ENV_DIR/orchestrator.env and confirm sidecar base URLs/paths"
echo "  2) (Optional) adjust planning assumptions and OpenAI settings"
echo "  3) Run: docker compose -f infra/docker-compose.yml up -d"
