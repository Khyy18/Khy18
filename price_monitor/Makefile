.PHONY: dev backend bot frontend admin build infra

# Запуск всех сервисов параллельно
dev:
	$(MAKE) -j3 backend bot frontend

# Backend (FastAPI)
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

# Telegram бот
bot:
	cd bot && python -m bot.main

# Frontend (Telegram Mini App)
frontend:
	cd frontend && npm run dev

# Admin панель
admin:
	cd admin && npm run dev

# Сборка фронтендов
build:
	cd frontend && npm run build
	cd admin && npm run build

# Инфраструктура (PostgreSQL, Redis, Nginx)
infra:
	cd infra && docker-compose up -d
