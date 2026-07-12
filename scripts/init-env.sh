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

cp_if_missing "$ENV_DIR/orchestrator.env.example" "$ENV_DIR/orchestrator.env"

# Fill the workspace secret key token on fresh env files only (existing
# installs keep their current key source so secrets stay decryptable).
if grep -q '__BUILDWEALTH_SECRET_KEY__' "$ENV_DIR/orchestrator.env"; then
  replace_token "$ENV_DIR/orchestrator.env" "__BUILDWEALTH_SECRET_KEY__" "$(openssl rand 32 | openssl base64 -A | tr '+/' '-_')"
  echo "Generated BUILDWEALTH_SECRET_KEY in orchestrator.env"
fi

echo ""
echo "Environment files are ready."
echo "Next:"
echo "  1) Open $ENV_DIR/orchestrator.env and confirm OpenAI/OpenBB settings"
echo "  2) Start standalone mode: docker compose -f infra/docker-compose.yml up -d orchestrator"
