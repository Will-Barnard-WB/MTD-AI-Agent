.PHONY: setup test lint demo

setup:
	python -m pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

demo:
	python -m mtd_agent.cli demo   # built in Stream B; will not run until then
