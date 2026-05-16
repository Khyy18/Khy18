# AI Text Agency

Freelance automation and text services platform powered by AI.

## Key Modules

- **Freelance Automation** - automated scanning and responding on Kwork/FL.ru with stealth browser
- **CRM** - customer lifecycle management with Telegram integration
- **Payments** - Telegram Stars payments with webhook retry queue
- **Content Generator** - RAG-based content generation for channels and blogs
- **Support Chatbot** - AI-powered customer support with knowledge base
- **Lead Scoring** - ML-based lead prioritization and auto-response
- **Fraud Detection** - order fraud risk scoring with AI analysis
- **Churn Prediction** - customer churn risk prediction and proactive actions
- **Viral/Referral** - referral program with bonus notifications
- **Ad Testing** - A/B testing with Thompson Sampling for ad creatives
- **Legal** - automated offer/contract PDF generation
- **Pricing** - dynamic pricing with demand-based multipliers

## Infrastructure

- **Monitoring** - Prometheus metrics, alerting to Telegram
- **Backup** - scheduled S3 backups with retention policy
- **Rate Limiting** - token bucket with Redis backend
- **Task Queue** - ARQ (asyncio Redis queue) for background jobs
- **Health Server** - HTTP health-check endpoint with DB/Redis status
- **Sentry** - error tracking and breadcrumbs

## Quick Start

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in your API keys and configuration in `.env`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   python -m playwright install --with-deps chromium
   ```

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Run the agency:
   ```bash
   python main.py
   ```

## Running Tests

```bash
pytest tests/ -v --tb=short
```
