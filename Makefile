setup: install_poetry install install_pre_commit tests

install:
	poetry install

install_poetry:
	curl -sSL https://install.python-poetry.org | python -

install_pre_commit:
	pre-commit install

tests:
	poetry run pre-commit run --all-files
