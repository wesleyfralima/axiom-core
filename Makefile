format:
	poetry run ruff format .

lint:
	poetry run ruff check .

lint-fix:
	poetry run ruff check . --fix

typecheck:
	poetry run mypy

test:
	poetry run pytest

coverage:
	poetry run pytest --cov=a_core --cov=b_domain --cov=c_application --cov-report=term --cov-report=html

check:
	poetry run ruff format --check .
	poetry run ruff check .
	poetry run mypy
	poetry run pytest --cov=a_core --cov=b_domain --cov=c_application
