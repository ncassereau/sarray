.PHONY: format check check-fix ty test

format:
	@uvx ruff format

check:
	@uvx ruff check

check-fix:
	@uvx ruff check --fix

ty:
	@uvx ty check

test:
	@uv run pytest tests/ -vvv
