# AI Outbound Agency - API Reference

## Overview

Base URL: `http://localhost:8000`

All authenticated endpoints require a Bearer token in the `Authorization` header:
```
Authorization: Bearer <access_token>
```

---

## Authentication

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/api/auth/register` | Register a new user and tenant | No |
| POST | `/api/auth/login` | Login and receive access token | No |
| POST | `/api/auth/refresh` | Refresh an access token | Yes |
| GET | `/api/auth/me` | Get current authenticated user info | Yes |

### POST /api/auth/register
Creates a new tenant and user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "tenant_name": "My Company"
}
```

### POST /api/auth/login
Authenticates a user and returns a JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## Campaigns

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/api/campaigns/` | Create a new campaign | Yes |
| GET | `/api/campaigns/` | List all campaigns for tenant | Yes |
| GET | `/api/campaigns/{id}` | Get campaign details | Yes |
| PUT | `/api/campaigns/{id}` | Update campaign | Yes |
| DELETE | `/api/campaigns/{id}` | Delete/archive campaign | Yes |
| POST | `/api/campaigns/{id}/activate` | Activate a campaign | Yes |
| POST | `/api/campaigns/{id}/pause` | Pause a campaign | Yes |

### POST /api/campaigns/
Create a new campaign with ICP filter and sequence configuration.

**Request Body:**
```json
{
  "name": "Q1 Outbound",
  "icp_filter": {"industry": "technology", "company_size": "50-500"},
  "sequence_id": "uuid-optional"
}
```

---

## Leads

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/api/leads/` | Create a new lead | Yes |
| GET | `/api/leads/` | List leads with filters | Yes |
| GET | `/api/leads/{id}` | Get lead details | Yes |
| POST | `/api/leads/import` | Bulk import leads from CSV | Yes |
| GET | `/api/leads/hot` | Get hot leads (high score) | Yes |

### POST /api/leads/
Create a new lead in the tenant's database.

**Request Body:**
```json
{
  "email": "lead@company.com",
  "first_name": "John",
  "last_name": "Doe",
  "company": "Acme Inc",
  "title": "VP of Sales",
  "linkedin_url": "https://linkedin.com/in/johndoe"
}
```

### POST /api/leads/import
Upload a CSV file with lead data for bulk import.

**Request:** multipart/form-data with `file` field.

---

## Voice

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/api/voice/scripts` | Create a call script | Yes |
| GET | `/api/voice/scripts` | List call scripts | Yes |
| GET | `/api/voice/scripts/{id}` | Get script details | Yes |
| PUT | `/api/voice/scripts/{id}` | Update a call script | Yes |
| GET | `/api/voice/calls` | List calls | Yes |
| GET | `/api/voice/calls/{id}` | Get call details | Yes |
| POST | `/api/voice/test-call` | Initiate a test call | Yes |
| GET | `/api/voice/stats` | Get voice channel statistics | Yes |

### POST /api/voice/scripts
Create a new call script for voice AI.

**Request Body:**
```json
{
  "name": "Discovery Call",
  "script_json": {
    "greeting_template": "Hi {{first_name}}, this is...",
    "topics": ["product_demo", "pricing"],
    "objection_handlers": {}
  },
  "voice_id": "default",
  "language": "en"
}
```

### POST /api/voice/test-call
Initiate a test call to verify script and voice configuration.

**Request Body:**
```json
{
  "phone_number": "+1234567890",
  "script_id": "uuid",
  "lead_id": "uuid"
}
```

---

## Billing

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| GET | `/api/billing/plans` | List available plans | Yes |
| GET | `/api/billing/subscription` | Get current subscription | Yes |
| POST | `/api/billing/checkout` | Create checkout session | Yes |
| GET | `/api/billing/usage` | Get current usage stats | Yes |
| GET | `/api/billing/invoices` | List billing invoices | Yes |
| POST | `/api/billing/voice-addon` | Subscribe to voice add-on | Yes |

### GET /api/billing/plans
Returns all available subscription plans with limits and pricing.

**Response:**
```json
[
  {
    "name": "starter",
    "price_cents": 2900,
    "leads_limit": 500,
    "emails_limit": 1000,
    "linkedin_limit": 100,
    "voice_calls_limit": 0
  }
]
```

### POST /api/billing/checkout
Creates a Stripe checkout session for plan upgrade.

**Request Body:**
```json
{
  "plan_name": "growth"
}
```

---

## Analytics

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| GET | `/api/analytics/funnel` | Get conversion funnel data | Yes |
| GET | `/api/analytics/timeline` | Get activity timeline | Yes |
| GET | `/api/analytics/top-sequences` | Get best-performing sequences | Yes |

### GET /api/analytics/funnel
Returns lead funnel metrics showing conversion through each stage.

**Query Parameters:**
- `days` (int, optional): Number of days to analyze (default: 30)

### GET /api/analytics/timeline
Returns daily activity metrics over the specified period.

**Query Parameters:**
- `days` (int, optional): Number of days (default: 30)
- `metric` (str, optional): Specific metric to return

---

## Onboarding

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/api/onboarding/step/1` | Complete step 1 (SMTP setup) | Yes |
| POST | `/api/onboarding/step/2` | Complete step 2 (ICP upload) | Yes |
| POST | `/api/onboarding/step/3` | Complete step 3 (Campaign setup) | Yes |
| POST | `/api/onboarding/step/4` | Complete step 4 (Activation) | Yes |
| GET | `/api/onboarding/status` | Get onboarding progress | Yes |

### POST /api/onboarding/step/1
Configure SMTP settings for email sending.

**Request Body:**
```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "user@gmail.com",
  "smtp_password": "app-password"
}
```

---

## Integrations

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/api/integrations/webhooks` | Register a webhook | Yes |
| GET | `/api/integrations/webhooks` | List registered webhooks | Yes |
| DELETE | `/api/integrations/webhooks/{id}` | Remove a webhook | Yes |
| POST | `/api/integrations/crm/sync` | Trigger CRM sync | Yes |
| GET | `/api/integrations/crm/status` | Get CRM sync status | Yes |

### POST /api/integrations/webhooks
Register a webhook for event notifications.

**Request Body:**
```json
{
  "url": "https://your-app.com/webhook",
  "events": ["lead.created", "lead.replied", "call.completed"],
  "secret": "your-webhook-secret"
}
```

**Supported Events:**
- `lead.created` - New lead added
- `lead.replied` - Lead replied to outreach
- `lead.qualified` - Lead marked as qualified
- `call.completed` - Voice call finished
- `meeting.booked` - Meeting scheduled
- `campaign.completed` - Campaign finished

---

## Health & Monitoring

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| GET | `/health` | Basic health check | No |
| GET | `/health/detailed` | Detailed health with service status | No |
| GET | `/metrics` | Prometheus metrics | Optional |

---

## Webhooks (Inbound)

| Method | Path | Description | Auth Required |
|--------|------|-------------|:---:|
| POST | `/webhooks/reply` | Handle inbound email reply | No |
| POST | `/api/voice/webhooks/status` | Twilio call status callback | No |
| POST | `/api/voice/webhooks/gather` | Twilio gather callback | No |
| POST | `/api/billing/webhook` | Stripe webhook events | No |

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error description"
}
```

Common HTTP status codes:
- `400` - Bad Request (validation error)
- `401` - Unauthorized (missing or invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (duplicate resource)
- `422` - Unprocessable Entity (validation failure)
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error
- `503` - Service Unavailable

---

## Rate Limiting

API requests are rate-limited per tenant:
- Default: 100 requests/minute
- Bulk operations: 10 requests/minute
- Voice calls: Subject to plan limits

Rate limit headers are included in responses:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000000
```
