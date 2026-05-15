.PHONY: build up down test logs backup restart shell status clean

# Docker Compose targets
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart: down up

logs:
	docker-compose logs -f

shell:
	docker-compose exec bot /bin/bash

status:
	docker-compose ps

# Development targets
test:
	python -m pytest tests/ -v

backup:
	python -c "import asyncio; from backup import backup_database; asyncio.run(backup_database())"

clean:
	docker-compose down -v --rmi local
