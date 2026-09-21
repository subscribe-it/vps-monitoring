# Wygodne skróty do tego, co i tak trzeba robić ręcznie.
# Wymaga: docker, python3; dla `panel-*` także pnpm.
SHELL := /bin/bash
COMPOSE := docker compose -f docker-compose.yml
DUMMY_ENV := PANEL_AUTH_PASSWORD_HTPASSWD='admin:$$apr1$$x$$y' GRAFANA_ADMIN_PASSWORD=dummy

.PHONY: help validate validate-compose validate-prometheus validate-promtool validate-loki validate-grafana test test-python build build-% up down logs ps

help:
	@echo "make validate          — pełna walidacja (to samo co CI, lokalnie)"
	@echo "make test              — testy serwisów Pythona"
	@echo "make build             — zbuduj wszystkie obrazy lokalnie"
	@echo "make up / down / ps / logs — lokalny stack (wymaga /tmp/mon-local)"
	@echo "make validate-promtool — testy reguł alertów (dowód, że progi działają)"

validate: validate-compose validate-prometheus validate-promtool validate-loki validate-grafana test

validate-compose:
	@$(DUMMY_ENV) $(COMPOSE) config > /dev/null && echo "✓ compose"
	@$(DUMMY_ENV) $(COMPOSE) config | grep -qE '^\s+ports:' && { echo "✗ stack publikuje porty!"; exit 1; } || echo "✓ zero publikowanych portów"

validate-prometheus:
	@docker run --rm -v "$(PWD)/config/prometheus:/p:ro" --entrypoint /bin/sh \
	  prom/prometheus:v3.14.0 -c '/bin/promtool check config /p/prometheus.yml && /bin/promtool check rules /p/alerts/*.yml' > /dev/null && echo "✓ prometheus: config + reguły"

validate-promtool:
	@docker run --rm -v "$(PWD)/config/prometheus:/p:ro" --entrypoint /bin/sh \
	  prom/prometheus:v3.14.0 -c 'for f in /p/tests/*.yml; do /bin/promtool test rules "$$f" >/dev/null || exit 1; done' && echo "✓ testy reguł alertów"

validate-loki:
	@docker run --rm -v "$(PWD)/config/loki:/l:ro" -e LOKI_RETENTION=720h \
	  grafana/loki:3.6.17 -config.file=/l/loki-config.yaml -config.expand-env=true -verify-config=true 2>&1 | tail -1

validate-grafana:
	@python3 -c "import glob,json,yaml; [json.load(open(f)) for f in glob.glob('config/grafana/dashboards/*.json')]; [yaml.safe_load(open(f)) for f in glob.glob('config/grafana/provisioning/**/*.yml', recursive=True)]" && echo "✓ grafana: dashboardy + provisioning"

test: test-python

test-python:
	@python3 -m compileall -q services && python3 -m unittest discover -s tests 2>&1 | tail -3

build:
	@for spec in "prometheus:dockerfiles/prometheus/Dockerfile:." "alertmanager:dockerfiles/alertmanager/Dockerfile:." \
	             "loki:dockerfiles/loki/Dockerfile:." "promtail:dockerfiles/promtail/Dockerfile:." \
	             "grafana:dockerfiles/grafana/Dockerfile:." "auth:dockerfiles/auth/Dockerfile:." \
	             "discovery:services/discovery/Dockerfile:services/discovery" \
	             "notifier:services/notifier/Dockerfile:services/notifier" \
	             "health-ping:services/health-ping/Dockerfile:services/health-ping" \
	             "panel:panel/Dockerfile:panel"; do \
	  name="$${spec%%:*}"; rest="$${spec#*:}"; df="$${rest%%:*}"; ctx="$${rest#*:}"; \
	  printf '  %-14s ' "$$name"; docker build -q -t "local/$$name:test" -f "$$df" "$$ctx" >/dev/null && echo "✓" || echo "✗"; \
	done

up:
	@docker compose --project-name monlocal --env-file /tmp/mon-local/.env \
	  -f docker-compose.yml -f /tmp/mon-local/override.yml up -d && echo "✓ stack wstał (monlocal)"

down:
	@docker compose --project-name monlocal --env-file /tmp/mon-local/.env \
	  -f docker-compose.yml -f /tmp/mon-local/override.yml down -v

ps:
	@docker compose --project-name monlocal ps --format 'table {{.Service}}\t{{.Status}}'

logs:
	@docker compose --project-name monlocal logs --tail 50
