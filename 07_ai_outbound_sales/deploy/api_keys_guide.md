# API Keys Guide

## Overview

AI Outbound Agency requires several API keys to function. This guide walks you through obtaining each one.

---

## OpenAI API Key

Used for: Email copywriting, lead research analysis, reply classification.

1. Go to [platform.openai.com](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to API Keys (Settings -> API Keys)
4. Click "Create new secret key"
5. Name it (e.g., "AI Outbound Production")
6. Copy and save the key (starts with `sk-`)

**Recommended model:** `gpt-4` (set via `LLM_OPENAI_MODEL` in .env)

**Estimated cost:** ~$20-50/month depending on volume.

---

## Anthropic API Key

Used for: Fallback LLM provider, complex reply handling.

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to API Keys
4. Click "Create Key"
5. Copy the key (starts with `sk-ant-`)

**Recommended model:** `claude-3-sonnet-20240229` (set via `LLM_ANTHROPIC_MODEL`)

**Estimated cost:** ~$10-30/month as a fallback provider.

---

## Groq API Key

Used for: Fast, low-cost LLM for simple tasks (optional fallback).

1. Go to [console.groq.com](https://console.groq.com/)
2. Sign up or log in
3. Navigate to API Keys
4. Click "Create API Key"
5. Copy the key (starts with `gsk_`)

**Recommended model:** `llama3-8b-8192`

**Estimated cost:** Free tier available, then pay-as-you-go.

---

## Apollo API Key

Used for: Lead research and enrichment, finding prospects matching your ICP.

1. Go to [app.apollo.io](https://app.apollo.io/)
2. Sign up for a plan (Free tier: 50 credits/month)
3. Navigate to Settings -> Integrations -> API
4. Generate an API key
5. Copy the key

**Recommended plan:** Professional ($49/month) for 2,000 credits.

**Note:** Each lead lookup costs 1 credit.

---

## Hunter API Key

Used for: Email verification and finding email addresses.

1. Go to [hunter.io](https://hunter.io/)
2. Sign up (Free tier: 25 searches/month)
3. Navigate to API section in your dashboard
4. Copy your API key

**Recommended plan:** Starter ($49/month) for 500 searches.

---

## Stripe Keys

Used for: Subscription billing, payment processing.

### Secret Key (Backend)

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com/)
2. Sign up or log in
3. Navigate to Developers -> API Keys
4. Copy the "Secret key" (starts with `sk_test_` for test mode, `sk_live_` for production)

### Webhook Secret

1. In Stripe Dashboard, go to Developers -> Webhooks
2. Add an endpoint: `https://yourdomain.com/api/billing/webhook`
3. Select events: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted`, `customer.subscription.updated`
4. Copy the webhook signing secret (starts with `whsec_`)

### Publishable Key

1. In Developers -> API Keys
2. Copy the "Publishable key" (starts with `pk_test_` or `pk_live_`)

**Important:** Use test keys (`sk_test_`, `pk_test_`) during development. Switch to live keys only for production.

---

## Optional: Telegram Bot

Used for: Real-time notifications and alerts.

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow prompts to name your bot
4. Copy the bot token
5. Add the bot to your notification group/channel
6. Get your chat ID:
   - Send a message to the bot
   - Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Find `chat.id` in the response

---

## Environment Variable Summary

After obtaining all keys, add them to your `.env` file:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
APOLLO_API_KEY=...
HUNTER_API_KEY=...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-100...
```
