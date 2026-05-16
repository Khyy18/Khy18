# AI Outbound Agency

Autonomous AI-powered outbound sales agent system. Uses LLM agents orchestrated via LangGraph to research prospects, enrich data, craft personalized messages, and manage multi-channel outreach campaigns.

## Architecture

```
+------------------+     +------------------+     +------------------+
|   Data Sources   |     |   LLM Agents     |     |   Channels       |
|  (Apollo, Hunter)|---->|  (Orchestrator,  |---->|  (Email, LinkedIn)|
|                  |     |   Researcher,    |     |                  |
|                  |     |   Enricher,      |     |                  |
|                  |     |   Copywriter)    |     |                  |
+------------------+     +------------------+     +------------------+
        |                        |                        |
        v                        v                        v
+--------------------------------------------------------------+
|                    PostgreSQL (AsyncPG)                       |
|   Tenants | Leads | Campaigns | Sequences | Messages | Events|
+--------------------------------------------------------------+
        |                        |
        v                        v
+------------------+     +------------------+
|   Redis          |     |   Scheduler      |
|  (Rate Limiting, |     |  (Campaign       |
|   Caching)       |     |   Execution)     |
+------------------+     +------------------+
        |
        v
+------------------+
|   Compliance     |
|  (Rate Limiter,  |
|   Opt-out)       |
+------------------+
```

## Pipeline Flow

1. **Research** - Agent queries Apollo.io for ICP-matching leads
2. **Enrich** - Agent verifies emails via Hunter.io, enriches data
3. **Score** - Lead scoring based on enrichment data and ICP fit
4. **Copywrite** - AI generates personalized outreach sequences
5. **Send** - Multi-channel delivery (email, LinkedIn)
6. **Track** - Event tracking (opens, clicks, replies, bounces)
7. **Respond** - AI handles inbound replies and books meetings

## Setup

### Docker Compose (Recommended)

```bash
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

### Manual Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Start the application
python main.py
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL async connection string | Yes |
| `REDIS_URL` | Redis connection URL | Yes |
| `OPENAI_API_KEY` | OpenAI API key for LLM | Yes |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | Yes |
| `GROQ_API_KEY` | Groq API key for fast inference | Yes |
| `APOLLO_API_KEY` | Apollo.io API key for lead search | Yes |
| `HUNTER_API_KEY` | Hunter.io API key for email verification | Yes |
| `SMTP_HOST` | SMTP server hostname | Yes |
| `SMTP_PORT` | SMTP server port | Yes |
| `SMTP_USER` | SMTP username | Yes |
| `SMTP_PASSWORD` | SMTP password | Yes |
| `APP_HOST` | Application host (default: 0.0.0.0) | No |
| `APP_PORT` | Application port (default: 8000) | No |

## Directory Structure

```
ai-outbound-agency/
|-- core/              # Core infrastructure
|   |-- config.py      # Pydantic settings (env vars)
|   |-- db.py          # Async SQLAlchemy engine + sessions
|   |-- models.py      # ORM models (Tenant, Lead, Campaign, etc.)
|   |-- llm.py         # Universal LLM client (OpenAI, Anthropic, Groq)
|-- agents/            # LangGraph AI agents
|-- data/
|   |-- sources/       # External data source clients
|   |   |-- apollo.py  # Apollo.io people/company search
|   |   |-- hunter.py  # Hunter.io email verification
|   |-- verification.py # Email verification orchestrator
|-- channels/
|   |-- email/         # Email sending logic
|   |-- linkedin/      # LinkedIn outreach
|-- scheduler/         # Campaign scheduling
|-- dashboard/         # FastAPI dashboard endpoints
|-- compliance/        # Rate limiting, opt-out management
|   |-- rate_limiter.py # Redis sliding window rate limiter
|-- alembic/           # Database migrations
|-- main.py            # FastAPI application entry point
|-- docker-compose.yml # Docker services
|-- Dockerfile         # Application container
|-- requirements.txt   # Python dependencies
```

## Tech Stack

- **Python 3.11+** - Async everywhere
- **FastAPI** - Web framework
- **LangGraph** - Agent orchestration
- **SQLAlchemy (async)** - ORM with asyncpg driver
- **PostgreSQL** - Primary database
- **Redis** - Rate limiting, caching
- **OpenAI / Anthropic / Groq** - LLM providers
- **Alembic** - Database migrations
- **Pydantic** - Data validation and settings
