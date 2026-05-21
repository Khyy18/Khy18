# Price Monitor API

Backend REST API for the Price Monitor mobile app. Built with FastAPI, SQLAlchemy (async), and SQLite.

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env file and configure
cp .env.example .env

# Create data directory
mkdir -p data

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Authentication
- `POST /auth/register` - Register or login by telegram_id, returns JWT

### Deals
- `GET /deals` - Paginated product listings (query params: page, limit, category)
- `GET /deals/{id}` - Single deal with full price history

### Categories
- `GET /categories` - All categories with product counts

### Alerts
- `GET /alerts` - User's price alerts
- `POST /alerts` - Create new alert
- `PATCH /alerts/{id}` - Toggle alert active status
- `DELETE /alerts/{id}` - Delete alert

### Favorites
- `GET /favorites` - User's favorited products
- `POST /favorites/{product_id}` - Add to favorites
- `DELETE /favorites/{product_id}` - Remove from favorites

### Profile
- `GET /profile` - User profile with subscription info

### System
- `GET /health` - Health check

## Authentication

All endpoints except `/auth/register` and `/health` require a Bearer token in the Authorization header:

```
Authorization: Bearer <jwt_token>
```

## Tech Stack

- **FastAPI** - async web framework
- **SQLAlchemy 2.0** - async ORM with aiosqlite
- **Pydantic v2** - request/response validation
- **python-jose** - JWT token handling
- **uvicorn** - ASGI server
