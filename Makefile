SHELL := /bin/zsh

COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: init-env up down restart ps logs sync test

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

test:
	cd services/orchestrator && python3 -m pip install -e '.[dev]' >/dev/null && pytest -q
