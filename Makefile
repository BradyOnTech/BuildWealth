SHELL := /bin/zsh

COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: init-env up down restart ps logs sync sync-status service-status telemetry-runtime backup backup-list backup-restore protection-status protection-apply reliability-smoke-storage import-csv test

init-env:
	./scripts/init-env.sh

up:
	$(COMPOSE) up -d orchestrator

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart orchestrator

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

sync:
	curl -s -X POST http://localhost:8090/api/snapshot/sync | jq

sync-status:
	curl -s http://localhost:8090/api/sync/status | jq

service-status:
	curl -s http://localhost:8090/api/services/status | jq

telemetry-runtime:
	curl -s http://localhost:8090/api/telemetry/runtime | jq

backup:
	curl -s -X POST http://localhost:8090/api/storage/backups \
	  -H 'content-type: application/json' \
	  -d '{"reason":"manual_cli_backup"}' | jq

backup-list:
	curl -s http://localhost:8090/api/storage/backups | jq

backup-restore:
	@echo "Usage: make backup-restore BACKUP_ID=20260415T123456000000Z PRE_BACKUP=true"
	curl -s -X POST http://localhost:8090/api/storage/backups/restore \
	  -H 'content-type: application/json' \
	  -d "{\"backup_id\":\"$${BACKUP_ID}\",\"create_pre_restore_backup\":$${PRE_BACKUP:-true}}" | jq

protection-status:
	curl -s http://localhost:8090/api/storage/protection/status | jq

protection-apply:
	curl -s -X POST http://localhost:8090/api/storage/protection/apply \
	  -H 'content-type: application/json' \
	  -d "{\"protection_level\":\"$${LEVEL:-hardened}\",\"include_backups\":$${INCLUDE_BACKUPS:-false}}" | jq

reliability-smoke-storage:
	./scripts/reliability-smoke-storage.sh

import-csv:
	@echo "Usage: make import-csv FILE=broker.csv DRY_RUN=true"
	curl -s -X POST http://localhost:8090/api/import/csv \
	  -H 'content-type: application/json' \
	  -d "{\"path\":\"$${FILE}\",\"dry_run\":$${DRY_RUN:-true}}" | jq

test:
	cd services/orchestrator && python3 -m pip install -e '.[dev]' >/dev/null && pytest -q
