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

## Stripe Billing

Multi-tenant billing with three pricing tiers managed through Stripe.

### Plans

| Tier | Leads/Month | Domains | Price |
|------|-------------|---------|-------|
| Starter | 500 | 1 | $99/mo |
| Growth | 2,000 | 3 | $299/mo |
| Agency | 10,000 | Unlimited | $799/mo |

Usage is tracked per tenant and enforced against plan limits. Exceeding lead limits blocks new campaign sends until the next billing cycle or an upgrade.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/billing/plans` | List all available billing plans |
| POST | `/api/billing/checkout` | Create a Stripe Checkout session for plan subscription |
| GET | `/api/billing/usage` | Get current usage stats for the authenticated tenant |
| POST | `/api/billing/webhook` | Stripe webhook receiver for payment events |

### Configuration

Set the following environment variables:

```
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
```

## Tenant Onboarding

A guided 4-step onboarding flow ensures new tenants configure their account correctly before launching campaigns.

### Steps

1. **Step 1: Create Tenant** - Register company name and admin user
2. **Step 2: Connect SMTP** - Provide SMTP credentials; the system validates connectivity
3. **Step 3: Upload ICP** - Define Ideal Customer Profile (industry, company size, titles, geo)
4. **Step 4: Activate Campaign** - Launch first outreach campaign with generated sequences

Progress is tracked per tenant. Each step validates inputs before allowing progression.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/onboarding/step1` | Create tenant and admin user |
| POST | `/api/onboarding/step2` | Submit and validate SMTP credentials |
| POST | `/api/onboarding/step3` | Upload ICP targeting criteria |
| POST | `/api/onboarding/step4` | Activate first campaign |
| GET | `/api/onboarding/status` | Get current onboarding progress for tenant |

## CRM Webhook Integration

Push lead events to external CRM systems via configurable webhooks. Supports custom endpoints and pre-built templates for popular CRMs.

### Features

- Create, list, and delete webhook configurations per tenant
- Pre-built templates for **HubSpot** and **AmoCRM** with correct field mappings
- Test endpoint to send a sample payload and verify connectivity
- Auto-triggers on hot leads (leads scoring above threshold automatically fire webhooks)

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/integrations/webhooks` | Create a new webhook configuration |
| GET | `/api/integrations/webhooks` | List all webhooks for the tenant |
| DELETE | `/api/integrations/webhooks/{id}` | Delete a webhook by ID |
| POST | `/api/integrations/webhooks/{id}/test` | Send a test payload to verify webhook |

### Webhook Payload

When a lead event triggers, the system sends a POST request to the configured URL with:

```json
{
  "event": "lead.hot",
  "lead_id": "uuid",
  "email": "contact@company.com",
  "company": "Company Inc",
  "score": 85,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Weekly Reports

Automated weekly performance reports delivered via email or Telegram. Reports include key metrics with week-over-week delta comparisons.

### Metrics Included

- Total leads generated
- Emails sent and reply rate
- Meetings booked
- Hot leads identified
- Campaign performance breakdown
- Week-over-week delta for each metric

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reports/weekly` | Generate and return the weekly report on demand |
| PUT | `/api/reports/weekly/preferences` | Update delivery preferences (email/telegram, schedule) |

### Delivery Channels

- **Email** - HTML-formatted report sent to configured recipients
- **Telegram** - Summary delivered via the client Telegram bot

### Configuration

Set delivery preferences per tenant:

```json
{
  "delivery_channels": ["email", "telegram"],
  "recipients": ["admin@company.com"],
  "telegram_chat_id": "123456789"
}
```
