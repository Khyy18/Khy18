#!/usr/bin/env bash
set -e

echo "=== AI Outbound Agency Setup ==="
echo ""
echo "This script will configure your environment and start all services."
echo ""

# Prompt for API keys (using -sp to suppress echo for secrets)
read -sp "OpenAI API Key: " OPENAI_API_KEY
echo ""
read -sp "Anthropic API Key: " ANTHROPIC_API_KEY
echo ""
read -sp "Groq API Key (optional, press Enter to skip): " GROQ_API_KEY
echo ""
read -sp "Apollo API Key: " APOLLO_API_KEY
echo ""
read -sp "Hunter API Key: " HUNTER_API_KEY
echo ""
read -sp "Stripe Secret Key: " STRIPE_SECRET_KEY
echo ""
read -sp "Stripe Webhook Secret: " STRIPE_WEBHOOK_SECRET
echo ""
echo ""

# Database and Redis
read -p "PostgreSQL URL [postgresql+asyncpg://user:pass@localhost:5432/outbound]: " DATABASE_URL
DATABASE_URL=${DATABASE_URL:-"postgresql+asyncpg://user:pass@localhost:5432/outbound"}

read -p "Redis URL [redis://localhost:6379/0]: " REDIS_URL
REDIS_URL=${REDIS_URL:-"redis://localhost:6379/0"}

# SMTP settings
read -p "SMTP Host: " SMTP_HOST
read -p "SMTP Port [587]: " SMTP_PORT
SMTP_PORT=${SMTP_PORT:-587}
read -p "SMTP User: " SMTP_USER
read -sp "SMTP Password: " SMTP_PASSWORD
echo ""

# JWT
JWT_SECRET=$(openssl rand -hex 32)
echo "Generated JWT Secret: ${JWT_SECRET:0:8}..."

# Telegram notifications (optional)
read -p "Telegram Bot Token (optional): " TELEGRAM_BOT_TOKEN
read -p "Telegram Chat ID (optional): " TELEGRAM_CHAT_ID

echo ""
echo "Generating .env file..."

cat > .env << EOF
# Database
DATABASE_URL=${DATABASE_URL}
REDIS_URL=${REDIS_URL}

# LLM Providers
OPENAI_API_KEY=${OPENAI_API_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
GROQ_API_KEY=${GROQ_API_KEY}

# Lead Research
APOLLO_API_KEY=${APOLLO_API_KEY}
HUNTER_API_KEY=${HUNTER_API_KEY}

# SMTP
SMTP_HOST=${SMTP_HOST}
SMTP_PORT=${SMTP_PORT}
SMTP_USER=${SMTP_USER}
SMTP_PASSWORD=${SMTP_PASSWORD}
SMTP_DOMAINS=[]

# Stripe
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}

# Auth
JWT_SECRET_KEY=${JWT_SECRET}

# Tracking
TRACKING_BASE_URL=https://yourdomain.com
TRACKING_SECRET=$(openssl rand -hex 16)

# Notifications
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}

# App
APP_HOST=0.0.0.0
APP_PORT=8000
EOF

chmod 600 .env
echo ".env file created successfully (permissions set to 600)."
echo ""

# Start services
echo "Starting services with Docker Compose..."
docker compose up -d

echo ""
echo "Waiting for database to be ready..."
sleep 5

# Run migrations
echo "Running database migrations..."
docker compose exec app alembic upgrade head

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Dashboard: http://localhost:8000"
echo "API Docs:  http://localhost:8000/docs"
echo ""
echo "Next steps:"
echo "  1. Configure your sending domains (see deploy/domains_setup.md)"
echo "  2. Set up your VPS for production (see deploy/vps_setup.md)"
echo "  3. Create your first campaign at http://localhost:8000/onboarding"
echo ""
