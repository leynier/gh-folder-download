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
	uv export --locked --all-groups --no-emit-project --format requirements-txt | uv run --locked pip-audit --disable-pip --require-hashes -r /dev/stdin
	uv run --locked bandit -r gh_folder_download -q

build:
	uv build --no-sources

check: install lint typecheck test build
