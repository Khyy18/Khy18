.PHONY: help install test lint dev docker-up docker-down smoke

# Цель по умолчанию - показать справку
.DEFAULT_GOAL := help

## help: Показать список доступных команд
help:
	@echo "AI Office - доступные команды:"
	@echo ""
	@echo "  make install      Установить зависимости (Python + Frontend)"
	@echo "  make test         Запустить тесты (pytest)"
	@echo "  make lint         Проверить код (ruff check + format)"
	@echo "  make dev          Запустить сервер разработки (uvicorn --reload)"
	@echo "  make docker-up    Собрать и запустить в Docker"
	@echo "  make docker-down  Остановить Docker-контейнеры"
	@echo "  make smoke        Запустить smoke-тест"
	@echo ""

## install: Установить Python и Frontend зависимости
install:
	pip install -r requirements.txt
	cd frontend && npm install

## test: Запустить тесты
test:
	python -m pytest tests/ -q

## lint: Проверить стиль кода
lint:
	ruff check . && ruff format --check .

## dev: Запустить сервер разработки с hot-reload
dev:
	python -m uvicorn ai_office.api.main:app --reload --port 8000

## docker-up: Собрать и запустить контейнеры
docker-up:
	docker compose -f deploy/docker-compose.yml up -d --build

## docker-down: Остановить контейнеры
docker-down:
	docker compose -f deploy/docker-compose.yml down

## smoke: Запустить smoke-тест
smoke:
	bash scripts/smoke_test.sh
