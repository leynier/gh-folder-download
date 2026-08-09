.PHONY: install test integration lint typecheck build check

install:
	uv sync --locked --all-groups --all-extras

test:
	uv run pytest

integration:
	uv run pytest -m integration --no-cov

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run ty check

build:
	uv build --no-sources

check: install lint typecheck test build
