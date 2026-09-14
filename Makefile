.PHONY: install dev playground test lint eval

install:
	uv sync

dev:
	uv run adk api_server app

playground:
	uv run adk web

test:
	uv run pytest tests/ -xvs

lint:
	uv run ruff check --fix app/ tests/
	uv run ruff format app/ tests/

eval:
	uv run agents-cli eval run

eval-generate:
	uv run agents-cli eval generate

eval-grade:
	uv run agents-cli eval grade

run:
	uv run agents-cli run "$(PROMPT)"
