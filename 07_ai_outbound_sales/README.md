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

## Voice AI Channel (Calls)

AI-powered outbound voice calling capability that enables fully autonomous sales calls. The system initiates calls via Twilio, transcribes prospect speech in real-time using Deepgram, generates conversational responses through an LLM, and synthesizes natural-sounding voice replies with ElevenLabs TTS.

### Architecture

| Component | Role |
|-----------|------|
| **Twilio** | Telephony provider - initiates outbound calls, streams media via WebSocket |
| **Deepgram** | Real-time speech-to-text (STT) via streaming WebSocket API |
| **ElevenLabs** | Text-to-speech (TTS) synthesis with natural voice output |
| **LLM (OpenAI/Anthropic)** | Conversation engine with FSM-based dialog states |
| **CallManager** | Orchestrates the full call lifecycle and media stream |
| **VoiceScheduler** | Priority queue with timezone/concurrency limits |

### Call Flow

1. **Initiate** - VoiceScheduler dispatches a queued call via Twilio REST API
2. **Connect** - Twilio connects to the prospect, AMD detects voicemail vs. human
3. **Media Stream** - Twilio opens a WebSocket, streaming raw audio (mu-law 8kHz)
4. **STT Transcription** - Audio chunks are forwarded to Deepgram for real-time transcription
5. **LLM Response** - Finalized transcript is sent to the LLM conversation agent
6. **TTS Synthesis** - LLM response text is streamed through ElevenLabs for audio generation
7. **Audio Playback** - Synthesized audio is sent back to Twilio via the media WebSocket
8. **Loop** - Steps 4-7 repeat for each conversation turn until hangup or max duration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | Yes (for voice) |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token for API authentication | Yes (for voice) |
| `TWILIO_PHONE_NUMBER` | Outbound caller ID phone number | Yes (for voice) |
| `DEEPGRAM_API_KEY` | Deepgram API key for real-time STT | Yes (for voice) |
| `ELEVENLABS_API_KEY` | ElevenLabs API key for TTS synthesis | Yes (for voice) |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice ID (default: "default") | No |
| `VOICE_MAX_CALL_DURATION` | Maximum call duration in seconds (default: 180) | No |
| `VOICE_CONCURRENT_CALLS_LIMIT` | Max concurrent calls per tenant (default: 5) | No |
| `VOICE_CALLING_HOURS_START` | Earliest hour (UTC) to place calls (default: 9) | No |
| `VOICE_CALLING_HOURS_END` | Latest hour (UTC) to place calls (default: 20) | No |
| `VOICE_AMD_ENABLED` | Enable answering machine detection (default: true) | No |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/voice/calls` | List calls with filters (status, outcome, date range), paginated |
| GET | `/api/voice/calls/{id}` | Get single call detail with transcript |
| POST | `/api/voice/calls/{id}/replay` | Get recording URL for call playback |
| GET | `/api/voice/stats` | Aggregated voice call statistics and conversion rate |
| POST | `/api/voice/scripts` | Create a new call script |
| GET | `/api/voice/scripts` | List all call scripts for the tenant |
| PUT | `/api/voice/scripts/{id}` | Update a call script |
| DELETE | `/api/voice/scripts/{id}` | Delete a call script |
| POST | `/api/voice/test-call` | Initiate a test call to a phone number |
| POST | `/api/voice/twilio/status` | Twilio status callback webhook |
| POST | `/api/voice/twilio/amd` | Twilio answering machine detection callback |
| WS | `/api/voice/twilio/stream` | Twilio media stream WebSocket endpoint |

### Call Scripts

Call scripts define the personality, greeting template, topics, and voice settings for outbound calls. Each script is stored as a JSON document:

```json
{
  "greeting_template": "Hi {name}, this is {company}. Do you have a moment?",
  "personality": {
    "tone": "professional and friendly",
    "pace": "moderate"
  },
  "topics": ["product demo", "pricing", "scheduling"],
  "value_proposition": "We help companies increase sales efficiency by 40%",
  "company_name": "Acme Corp"
}
```

Scripts are assigned to campaigns or individual calls. The VoiceConversationAgent uses the script to guide dialog flow through states: greeting, qualification, offer, objection_handling, and closing.

### Billing

Voice calls are tracked per tenant with a `voice_calls_limit` on each billing plan. The Growth and Agency tiers include voice call allocations. Usage is enforced against plan limits, and exceeding the limit blocks new call scheduling until the next billing cycle or a plan upgrade.

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

## AI Agents (Deep Intelligence)

Advanced AI agents that optimize outbound sales operations through data analysis, ML predictions, and adaptive communication.

### Script Optimizer (`agents/script_optimizer.py`)

Analyzes call script performance by comparing transcripts with outcomes. Identifies which phrases and approaches correlate with successful calls (qualified leads) versus unsuccessful ones.

**Capabilities:**
- Analyze script performance across all calls using that script
- Generate optimization suggestions with confidence scores for each script section (greeting, qualification, offer, closing)
- Create A/B test variants from suggestions to validate improvements

**API Endpoints:**
- `GET /api/voice/scripts/{id}/optimization-suggestions` - Get actionable suggestions for a script

### Lead Timing Predictor (`agents/timing_predictor.py`)

ML model (Gradient Boosting) trained on historical call data to predict optimal contact times for leads. Uses features like timezone, industry, seniority level, day of week, and hour.

**Capabilities:**
- Train on historical call outcome data per tenant
- Predict best contact times for a specific lead (ranked time slots)
- Raw probability prediction for arbitrary feature combinations
- Handles insufficient training data gracefully (returns uniform distribution)

### Persona Adapter (`agents/persona_adapter.py`)

Detects lead persona type from enrichment data and adapts communication style. Uses rule-based detection with LLM fallback for ambiguous cases.

**Persona Types:** C_LEVEL, VP, DIRECTOR, MANAGER, TECHNICAL, STARTUP_FOUNDER, SMB_OWNER

**Capabilities:**
- Detect persona from title, company size, and industry data
- Generate PersonaProfile with formality level, technical depth, urgency preference, value framing, and tone
- Adapt messages to match persona communication style via LLM
- Provide voice-specific adjustments (pace, tone, vocabulary level) for voice calls

### Objection Handler (`agents/objection_handler.py`)

Extracts objections from call transcripts, builds a searchable library of objections with proven responses, and tracks success rates over time.

**Objection Categories:** pricing, timing, authority, need, competitor, technical

**Capabilities:**
- Extract objections from call transcripts using LLM
- Search the library for best responses to similar objections
- Record outcomes to update response success rates over time
- Batch-process historical calls to build the initial library

**API Endpoints:**
- `GET /api/voice/objections` - List objection library with pagination and category filter
- `POST /api/voice/objections/{id}/response` - Add a new response to an objection
- `GET /api/voice/objections/categories` - List categories with counts

**Database:** `objections` table (migration 013) with JSONB responses array tracking text, success_rate, and times_used per response.


## Production Deployment

The project includes a production-ready `docker-compose.prod.yml` for deploying the full stack.

### Services

- **nginx** - Reverse proxy and static file server (nginx:alpine)
- **certbot** - Automatic SSL certificate provisioning and renewal via Let's Encrypt
- **postgres** - PostgreSQL 16 Alpine with persistent volume
- **redis** - Redis 7 Alpine with persistent volume
- **backend** - The FastAPI application (built from Dockerfile)

### Setup

1. Copy and configure the environment file:
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

2. Update `deploy/nginx.conf` and replace `domain` in the SSL certificate paths with your actual domain name.

3. Obtain initial SSL certificates:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm certbot certonly \
     --webroot -w /var/www/certbot -d yourdomain.com
   ```

4. Build and start all services:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

5. Run database migrations:
   ```bash
   docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
   ```

### SSL Renewal

The certbot service automatically renews certificates every 12 hours. After renewal, reload nginx:
```bash
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

## CI/CD

The project uses GitHub Actions for continuous integration. The pipeline is defined in `.github/workflows/ci.yml` and triggers on pushes and pull requests to the `main` branch.

### Jobs

| Job | Description |
|-----|-------------|
| **lint** | Runs `ruff check .` for Python code linting |
| **test** | Installs dependencies and runs `pytest tests/ --tb=short` |
| **build-frontend** | Installs npm packages and runs `npm run build` |
| **docker-build** | Builds the Docker image to verify the Dockerfile is valid |

All jobs use Python 3.11 and Node 20, with pip and npm caching for faster runs.

## CORS Configuration

CORS (Cross-Origin Resource Sharing) is configured via the `CORS_ORIGINS` environment variable. Set it to a comma-separated list of allowed frontend origins.

Default value:
```
CORS_ORIGINS=http://localhost:5174,http://localhost:3000
```

In production, set this to your actual frontend domain(s):
```
CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
```

The middleware allows credentials, all HTTP methods, and all headers for the specified origins.

