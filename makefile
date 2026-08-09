.PHONY: install test integration lint typecheck security build check

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

security: install
	uv export --all-groups --format requirements-txt --no-hashes | uv run pip-audit -r /dev/stdin
	uv run bandit -r gh_folder_download -q

build:
	uv build --no-sources

check: install lint typecheck test build
