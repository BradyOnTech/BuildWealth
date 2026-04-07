SHELL := /bin/zsh

COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: init-env up down restart ps logs sync sync-status import-csv test

init-env:
	./scripts/init-env.sh

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

sync:
	curl -s -X POST http://localhost:8090/api/snapshot/sync | jq

sync-status:
	curl -s http://localhost:8090/api/sync/status | jq

import-csv:
	@echo "Usage: make import-csv FILE=broker.csv DRY_RUN=true"
	curl -s -X POST http://localhost:8090/api/import/csv \
	  -H 'content-type: application/json' \
	  -d "{\"path\":\"$${FILE}\",\"dry_run\":$${DRY_RUN:-true}}" | jq

test:
	cd services/orchestrator && python3 -m pip install -e '.[dev]' >/dev/null && pytest -q
