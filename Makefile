.PHONY: infra-up infra-down infra-logs init generate-data stream-local verify test lint dashboard

# --- Infrastructure -----------------------------------------------------------

infra-up:
	docker compose up -d --build

infra-down:
	docker compose down

infra-logs:
	docker compose logs -f telegraf timescaledb grafana

dashboard:
	@echo "Grafana:  http://localhost:3000  (admin / GF_SECURITY_ADMIN_PASSWORD in .env)"

# --- Data layer ---------------------------------------------------------------

init:
	uv run python -m scripts.init_db

generate-data:
	uv run python -m scripts.generate_history

verify:
	uv run python -m scripts.verify

stream-local:
	uv run python -m scripts.stream_vitals

# --- Quality gates ------------------------------------------------------------

test:
	uv run pytest

lint:
	uv run ruff check .