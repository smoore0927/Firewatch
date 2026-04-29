.PHONY: up down build logs backend frontend setup

up:
	docker compose up

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

backend:
	docker compose exec backend bash

frontend:
	docker compose exec frontend sh

setup:
	@if [ ! -f firewatch-backend/.env ]; then \
		cp firewatch-backend/.env.example firewatch-backend/.env; \
		echo "Created firewatch-backend/.env from .env.example"; \
		echo "Open it and set SECRET_KEY before running 'make up'"; \
	else \
		echo "firewatch-backend/.env already exists — skipping"; \
	fi
