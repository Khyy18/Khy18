# AI Text Agency

Production-grade Telegram bot platform for automated text content services (copywriting, rewriting, SEO, translations) with integrated payments, admin panel, REST API, and web landing page.

## Architecture

```
+-------------------+       +-------------------+       +-------------------+
|   Telegram Bot    |       |    Admin Bot      |       |   REST API        |
|  (bot.py)         |       |  (admin_bot.py)   |       |  (api/app.py)     |
+--------+----------+       +--------+----------+       +--------+----------+
         |                           |                           |
         +---------------------------+---------------------------+
                                     |
                    +----------------+----------------+
                    |          Core Services           |
                    |  pipeline.py | services.py      |
                    |  billing.py  | pricing.py       |
                    |  subscriptions.py               |
                    +----------------+----------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
+--------+----------+   +-----------+---------+   +-------------+-------+
|  Queue Manager    |   |     Database        |   |   Scheduler         |
|  (queue_manager)  |   |  (database.py)      |   |  (scheduler.py)     |
+-------------------+   +---------------------+   +-----------------------+
         |                           |                           |
+--------+----------+   +-----------+---------+   +-------------+-------+
|  Rate Limiter     |   |     Backup          |   |   Monitoring        |
|  (rate_limiter)   |   |  (backup.py)        |   |  (monitoring.py)    |
+-------------------+   +---------------------+   +-----------------------+
         |                           |                           |
+--------+----------+   +-----------+---------+   +-------------+-------+
|  CRM / Segments   |   |     Resilience      |   |   Logging Config    |
|  (crm.py)         |   |  (resilience.py)    |   |  (logging_config)   |
+-------------------+   +---------------------+   +-----------------------+
```

### Services (Docker Compose)

| Service     | Description                          | Port |
|-------------|--------------------------------------|------|
| `bot`       | Main Telegram client bot             | -    |
| `admin_bot` | Admin management bot                 | -    |
| `api`       | REST API for B2B integrations        | 8000 |
| `web`       | Landing page with analytics          | 8080 |
| `scheduler` | Background tasks (backup, CRM, etc.) | -    |

## Quick Start (Docker)

```bash
# 1. Clone and enter directory
cd ai_agency

# 2. Create environment file
cp .env.example .env
# Edit .env with your tokens and keys

# 3. Build and run all services
make build
make up

# 4. Check status
make status

# 5. View logs
make logs
```

## Manual Installation

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env

# 4. Run the application
python main_multi.py
```

## Configuration

All configuration is managed via environment variables. Copy `.env.example` to `.env` and fill in the values.

### Required Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token for the client-facing Telegram bot |
| `OPENAI_API_KEY` | OpenAI API key for text generation |
| `YOOKASSA_SHOP_ID` | YooKassa payment shop ID |
| `YOOKASSA_SECRET_KEY` | YooKassa secret key |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_ADMIN_BOT_TOKEN` | - | Token for admin bot |
| `ADMIN_TELEGRAM_ID` | `0` | Admin's Telegram user ID |
| `DEFAULT_MODEL` | `gpt-4o-mini` | Default LLM model |
| `DATABASE_PATH` | `agency.db` | SQLite database path |
| `GROQ_API_KEY` | - | Groq API key (fallback LLM) |
| `WEB_HOST` | `0.0.0.0` | Web server host |
| `WEB_PORT` | `8080` | Web server port |
| `API_HOST` | `0.0.0.0` | API server host |
| `API_PORT` | `8000` | API server port |
| `BOT_USERNAME` | - | Bot username for deep links |
| `BOT_PERSONA_NAME` | `Алиса` | Bot persona name |
| `BOT_PERSONA_GREETING` | `Привет! Я Алиса...` | Greeting message |
| `SENTRY_DSN` | - | Sentry DSN for error tracking |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | `logs/agency.log` | Log file path |
| `QUEUE_MAX_SIZE` | `100` | Max order queue size |
| `QUEUE_WORKERS` | `3` | Number of queue workers |
| `BACKUP_DIR` | `backups` | Backup directory |
| `BACKUP_KEEP_COUNT` | `7` | Number of backups to retain |
| `STARS_TO_RUB_RATE` | `1.5` | Telegram Stars to RUB conversion |
| `GOOGLE_ANALYTICS_ID` | - | Google Analytics tracking ID |
| `YANDEX_METRIKA_ID` | - | Yandex Metrika counter ID |
| `SUBSCRIPTION_BASIC_PRICE` | `990` | Basic subscription price (RUB) |
| `SUBSCRIPTION_BASIC_ORDERS` | `20` | Orders in Basic plan |
| `SUBSCRIPTION_PRO_PRICE` | `2490` | Pro subscription price (RUB) |
| `REFERRAL_BONUS_PERCENT` | `10` | Referral bonus percentage |
| `CHANNEL_ID` | - | Telegram channel for case posting |
| `KWORK_KEYWORDS` | `копирайтинг,...` | Keywords for lead parsing |
| `NICHE_BOTS` | `[]` | Multi-bot config (JSON) |

## Docker Deployment

### Build and Run

```bash
# Build all services
docker-compose build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop all
docker-compose down
```

### Volume Mounts

| Volume | Purpose |
|--------|---------|
| `app-data` | SQLite database persistence |
| `app-logs` | Application logs |
| `app-backups` | Database backups |

### Health Checks

All services include health checks:
- **bot/web**: `GET http://localhost:8080/health`
- **api**: `GET http://localhost:8000/api/orders`

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make build` | Build Docker images |
| `make up` | Start all services in background |
| `make down` | Stop all services |
| `make restart` | Restart all services |
| `make logs` | Follow logs from all services |
| `make shell` | Open shell in bot container |
| `make status` | Show service status |
| `make test` | Run test suite |
| `make backup` | Create database backup |
| `make clean` | Remove containers, volumes, and images |

## Module Descriptions

### Core Modules

| Module | Description |
|--------|-------------|
| `bot.py` | Main Telegram bot with conversation handlers for ordering |
| `admin_bot.py` | Admin bot with statistics, order management, CRM, monitoring |
| `main_multi.py` | Application entry point, starts bot + web + API concurrently |
| `config.py` | Centralized configuration from environment variables |
| `database.py` | SQLite async operations with aiosqlite |
| `models.py` | Data models and ServiceType enum |
| `services.py` | Service definitions (copywriting, rewriting, SEO, etc.) |

### Processing

| Module | Description |
|--------|-------------|
| `pipeline.py` | LLM processing pipeline with OpenAI + Groq fallback |
| `queue_manager.py` | Priority-based async order queue with worker pool |
| `resilience.py` | Retry with backoff, circuit breaker, graceful shutdown |

### Payments and Billing

| Module | Description |
|--------|-------------|
| `billing.py` | Balance management and order cost calculations |
| `pricing.py` | Dynamic pricing engine |
| `payment_gateway.py` | YooKassa payment integration |
| `telegram_payments.py` | Telegram Stars native payments |
| `subscriptions.py` | Subscription management (Basic/Pro plans) |

### Analytics and Marketing

| Module | Description |
|--------|-------------|
| `analytics.py` | Business analytics and reporting |
| `ab_testing.py` | A/B testing framework |
| `crm.py` | Client segmentation and personal offers |
| `auto_posting.py` | Automated case publishing to channel |
| `lead_parser.py` | Kwork lead parsing |

### Infrastructure

| Module | Description |
|--------|-------------|
| `logging_config.py` | Structured JSON logging with rotation |
| `monitoring.py` | Health checks, metrics, admin alerts |
| `backup.py` | Automated SQLite backup with rotation |
| `rate_limiter.py` | Per-user anti-spam and flood protection |
| `scheduler.py` | Background task scheduler |
| `scheduler_standalone.py` | Standalone scheduler entry point for Docker |

### Web and API

| Module | Description |
|--------|-------------|
| `web/app.py` | aiohttp landing page server |
| `web/templates/index.html` | Responsive landing with Tailwind CSS |
| `web/static/style.css` | Custom CSS overrides |
| `api/app.py` | FastAPI REST API |
| `api/auth.py` | API authentication |

### Utilities

| Module | Description |
|--------|-------------|
| `utils.py` | Telegram card formatting, progress bars, sparklines |
| `i18n.py` | Internationalization |
| `document_generator.py` | DOCX/PDF document generation |
| `bot_factory.py` | Multi-bot architecture factory |

### Voice and Vision

| Module | Description |
|--------|-------------|
| `voice_handler.py` | Voice/audio transcription via OpenAI Whisper API |
| `vision_handler.py` | Image text extraction via GPT-4o Vision |

### International Payments

| Module | Description |
|--------|-------------|
| `international_payments.py` | Stripe Checkout + NOWPayments crypto integration |

### Content and Marketing Automation

| Module | Description |
|--------|-------------|
| `content_farm.py` | Auto-generate and post content to Telegram channels |
| `upsell_agent.py` | Post-order add-on suggestions with AI-generated recommendations |
| `demo_generator.py` | Demo content and ad creative generation for all services |
| `marketplace.py` | Template marketplace with categories, preview, and purchase |

### B2B and White-Label

| Module | Description |
|--------|-------------|
| `whitelabel.py` | White-label bot management, revenue sharing, partner stats |

## Queue System

The order queue (`queue_manager.py`) provides:

- **Priority-based processing**: Urgent orders processed first
- **Configurable worker pool**: `QUEUE_WORKERS` concurrent processors
- **Backpressure**: When queue is full (`QUEUE_MAX_SIZE`), returns estimated wait time
- **Statistics**: Real-time queue size, active workers, average processing time
- **Graceful lifecycle**: Clean start/stop with in-progress order completion

```python
# Queue usage (internal)
from queue_manager import OrderQueue

queue = OrderQueue(max_size=100, worker_count=3)
await queue.start()
await queue.enqueue_order(order_id, service_type, input_text, priority=1)
stats = queue.get_queue_stats()
await queue.shutdown()
```

## Monitoring and Alerts

The monitoring system (`monitoring.py`) provides:

- **Health checks**: Database connectivity, OpenAI API, bot responsiveness
- **Metrics collection**: Orders in queue, processing time, error rate, uptime
- **Admin alerts**: Telegram notifications on critical failures
- **Watchdog**: Automatic alerting if bot is unresponsive for 5+ minutes

Health endpoint response:
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "ok"},
    "openai_api": {"status": "ok"},
    "bot": {"status": "ok"}
  },
  "metrics": {
    "orders_in_queue": 3,
    "avg_processing_time": 12.5,
    "error_rate": 0.02,
    "uptime": 86400
  }
}
```

## Logging

Structured logging with `logging_config.py`:

- **Console output**: Human-readable format for development
- **File output**: JSON format with rotation (10MB, 5 files)
- **Structured fields**: order_id, client_id, duration, status
- **Sentry integration**: Optional error tracking via `SENTRY_DSN`

Log levels controlled via `LOG_LEVEL` environment variable.

## Backup and Recovery

Automated backup system (`backup.py`):

- **Daily backups**: SQLite database copied with timestamp
- **Rotation**: Keeps last N backups (`BACKUP_KEEP_COUNT`, default 7)
- **Format**: `agency_backup_YYYYMMDD_HHMMSS.db`
- **Manual backup**: `make backup`

Recovery:
```bash
# List available backups
ls backups/

# Restore from backup
cp backups/agency_backup_20240101_120000.db agency.db
```

## Rate Limiting

Anti-spam protection (`rate_limiter.py`):

- **Order limit**: Max 5 orders per hour per user
- **Flood detection**: Ban if >20 messages per minute
- **Cooldown**: 30-second minimum between orders
- **In-memory**: Fast per-user tracking with automatic cleanup

## CRM and Segmentation

Client relationship management (`crm.py`):

| Segment | Criteria |
|---------|----------|
| `new` | Registered less than 7 days, 0 orders |
| `active` | Ordered in last 14 days |
| `vip` | Total spent > 5000 RUB |
| `sleeping` | No orders for 14+ days |

Features:
- Automatic segment recalculation (every 6 hours via scheduler)
- Personalized offers based on segment
- Client timeline view in admin bot

## Telegram Stars Payments

Native Telegram payment method (`telegram_payments.py`):

- No external payment provider needed
- Configurable conversion rate (`STARS_TO_RUB_RATE`)
- Automatic balance credit on successful payment
- Integrated alongside YooKassa in top-up menu

## Testing

```bash
# Run all tests
make test

# Run with verbose output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_queue.py -v
```

## API Reference

### REST API (port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/orders` | List orders (with pagination) |
| POST | `/api/orders` | Create new order |
| GET | `/api/orders/{id}` | Get order by ID |
| GET | `/api/clients` | List clients |
| GET | `/api/stats` | Service statistics |

Authentication: Bearer token in `Authorization` header.

### Web Endpoints (port 8080)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET | `/health` | Health check |
| GET | `/api/stats` | Public stats (total orders, rating) |

## Troubleshooting

### Bot not starting

1. Check `TELEGRAM_BOT_TOKEN` is set correctly
2. Verify bot token with: `curl https://api.telegram.org/bot<TOKEN>/getMe`
3. Check logs: `make logs` or `cat logs/agency.log`

### Orders stuck in queue

1. Check queue status in admin bot (Monitoring section)
2. Verify OpenAI API key is valid
3. Check if circuit breaker is open (5 consecutive LLM failures)
4. Restart workers: `make restart`

### Database errors

1. Check file permissions on `agency.db`
2. Verify volume mount in Docker: `docker-compose exec bot ls -la /app/data/`
3. Restore from backup if corrupted (see Backup and Recovery section)

### Payment failures

1. Verify YooKassa credentials in `.env`
2. Check webhook URL is accessible from internet
3. For Telegram Stars: ensure bot has payment capabilities enabled via @BotFather

### Health check failing

1. Check which component is down: `curl http://localhost:8080/health`
2. Review monitoring alerts in admin bot
3. Common issues:
   - Database locked: too many concurrent writes
   - OpenAI API: rate limit or invalid key
   - Bot: token revoked or network issue

### Docker issues

```bash
# Rebuild from scratch
make clean
make build
make up

# Check container logs
docker-compose logs bot --tail=50

# Enter container for debugging
make shell
```

## New Modules (v2)

### onboarding.py - Automated Onboarding Tour
4-step interactive tour for new users: service carousel, free trial offer, how-it-works demo, 20% bonus promo. Tracks drop-off analytics per step.

### demand_pricing.py - Dynamic Demand Pricing
Smart pricing based on real-time demand. Surge pricing (+10-20%) during peak hours, night/weekend discounts (-10-15%) during low demand.

### loyalty.py - Loyalty Program
4-tier loyalty system (Bronze/Silver/Gold/Platinum) based on total spending. Progressive discounts from 0% to 15%, priority queue, exclusive features.

### retargeting.py - Automated Retargeting
Scenario-based retargeting: reminds users who started but did not order, abandoned carts, marketplace viewers, and low-rating recovery. 24h cooldown per user.

### ad_copywriter.py - AI Ad Copy Generator
Generates 3 ad variants (short/medium/long) for any niche with A/B UTM tracking links. Supports formal/informal styles.

### platform_adapter.py + adapters/ - Multi-Platform Support
Abstract PlatformAdapter interface with concrete TelegramAdapter (working) and stubs for WhatsApp and VK. PlatformRouter for message routing.

### prompt_localizer.py - Prompt Localization
Automatic prompt translation for non-Russian clients. Caches translations in memory and DB. Integrates with pipeline.py for language-aware generation.

### realtime_dashboard.py - Real-Time WebSocket Dashboard
WebSocket endpoint at /ws/dashboard for live metric updates. Broadcasts new_order, payment, and rating events. Token-based auth. Auto-reconnect on frontend.

## New Modules (v3)

### llm_router.py - Multi-Provider LLM Router
Automatic provider switching: OpenAI -> Groq -> Anthropic -> Together.ai. Health checks every 5 minutes, auto-selects cheapest working provider. Circuit breaker integration for fault tolerance.

### fl_parser.py - FL.ru Lead Parser
Parses FL.ru freelance orders by category (texts, copywriting, translations, SEO). Human-like anti-detect with delays, daily limits, and working hours. AI-generated unique responses.

### tg_chat_parser.py - Telegram Chat Monitor
Monitors specified Telegram chats for order-related messages. Keywords detection, contextual AI responses, anti-spam (max 3 responses/hour/chat). Uses pyrogram userbot.

### support_handler.py - AI Live-Support
FAQ-based instant answers with LLM fallback for complex questions. Automatic admin escalation when AI is not confident. Detects questions by markers ("?", starts with "how/what/why").

### Money-back Guarantee
Automatic refund to balance on low rating (1-2 stars). User choice: free redo or keep funds on balance. Guarantee text in welcome message. Full refund stats via get_moneyback_stats().

### db_postgres.py - PostgreSQL Backend
Alternative to SQLite for production deployments. Same async interface, asyncpg-based connection pool, PostgreSQL-native types. Migration script from SQLite included. Selectable via DATABASE_BACKEND config.

### redis_backend.py - Redis Support
Optional Redis backend for: order queues (LPUSH/RPOP), prompt/result cache with TTL, sliding window rate limiting, user session storage. Graceful fallback when Redis unavailable. Health check endpoint.
