# Shelf-to-Shop developer commands. Recipes are plain uv/pre-commit calls so they run under
# GNU make on Linux, macOS and Windows (ezwinports make or Git Bash).

.PHONY: help setup lint fmt test check api spike-auth spike-4 spike-5

help:
	@echo "setup       install Python deps and git hooks"
	@echo "lint        ruff, mypy and module-boundary checks"
	@echo "api         run the API locally on http://localhost:8000"
	@echo "fmt         apply ruff fixes and formatting"
	@echo "test        run the Python test suite"
	@echo "check       lint + test"
	@echo "spike-auth  call Meta and Baseten once with the keys from .env"
	@echo "spike-4     background replacement spike (Muse Image + SAM 3.1)"
	@echo "spike-5     serve the recorder spike on http://localhost:8080 (see spikes/05_recorder/README.md)"

setup:
	uv sync
	pre-commit install --hook-type pre-commit --hook-type commit-msg

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

check: lint test

api:
	uv run uvicorn --factory shelf.main:create_app --reload --port 8000

spike-auth:
	uv run python spikes/00_auth_check.py

spike-4:
	uv run python spikes/04_background.py

spike-5:
	uv run python -m http.server 8080 --bind 127.0.0.1 --directory spikes/05_recorder
