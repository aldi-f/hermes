.PHONY: install test test-cov lint build dev-run dev-redis deploy logs clean release help

help:
	@echo "Hermes - Alertmanager Routing and Distribution System"
	@echo ""
	@echo "Usage:"
	@echo "  make install     Install dependencies"
	@echo "  make test        Run tests"
	@echo "  make test-cov    Run tests with coverage"
	@echo "  make lint        Run linter"
	@echo "  make build       Build Docker image"
	@echo "  make dev-run     Run locally"
	@echo "  make dev-redis   Run Redis locally"
	@echo "  make deploy      Deploy to Kubernetes"
	@echo "  make logs        Show pod logs"
	@echo "  make release     Create and push a release tag (usage: make release VERSION=v1.0.0)"
	@echo "  make clean       Clean up"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

lint:
	ruff check src/ tests/

build:
	docker build -t hermes:latest .

dev-run:
	python -m src.main

dev-redis:
	docker run -d --name hermes-redis -p 6379:6379 redis:7-alpine

deploy:
	kubectl apply -k k8s/overlays/prod

logs:
	kubectl logs -l app=hermes -f --tail=100

clean:
	rm -rf .pytest_cache .coverage htmlcov *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

release:
ifndef VERSION
	@echo "Error: VERSION is required"
	@echo "Usage: make release VERSION=v1.0.0"
	@exit 1
endif
	@echo "Running tests before release..."
	@$(MAKE) test
	@echo "Checking for uncommitted changes..."
	@git diff-index --quiet HEAD -- || (echo "Error: Uncommitted changes exist. Commit or stash them first." && exit 1)
	@echo "Creating tag $(VERSION)..."
	@git tag $(VERSION)
	@echo "Pushing tag to origin..."
	@git push origin $(VERSION)
	@echo "Release $(VERSION) created! Check GitHub Actions for Docker build status."