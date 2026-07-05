.PHONY: help up down backend-check frontend-check test

help:
	@echo "Targets:"
	@echo "  up              Build and start the full stack (docker compose)"
	@echo "  down            Stop the stack and remove volumes"
	@echo "  backend-check   Run ruff, mypy, and pytest in backend/"
	@echo "  frontend-check  Run tsc, eslint, and build in frontend/"
	@echo "  test            Run backend and frontend checks"

up:
	docker compose up --build

down:
	docker compose down -v

backend-check:
	cd backend && ruff check suas tests && mypy suas && pytest -q

frontend-check:
	cd frontend && npm run typecheck && npm run lint && npm run build

test: backend-check frontend-check
