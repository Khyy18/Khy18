# AI Office

Multi-agent AI system for office automation with specialized agents, FastAPI backend, and Telegram interface.

## Features

- Multiple specialized AI agents for different tasks
- FastAPI REST API for programmatic access
- Telegram client for conversational interface
- SQLAlchemy-based persistent memory
- Alembic database migrations

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run database migrations:
   ```bash
   alembic upgrade head
   ```

3. Run the application:
   ```bash
   python main.py
   ```

## Running Tests

```bash
pytest tests/ -v --tb=short
```
