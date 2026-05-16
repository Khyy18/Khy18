from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    redis_url: str
    openai_api_key: str
    anthropic_api_key: str
    groq_api_key: str
    apollo_api_key: str
    hunter_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # IMAP settings
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""

    # Multiple SMTP domains (JSON string of domain configs)
    smtp_domains: str = "[]"

    # Tracking
    tracking_base_url: str = "http://localhost:8000"
    tracking_secret: str = "change-me-in-production"

    # Calendar integration
    calendar_provider: str = "calcom"
    calcom_api_key: str = ""
    calcom_base_url: str = "https://api.cal.com/v1"
    google_calendar_credentials_json: str = ""

    # JWT Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    # Stripe billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # LinkedIn settings
    linkedin_session_dir: str = "./linkedin_sessions"
    linkedin_max_connections_per_day: int = 25
    linkedin_max_messages_per_day: int = 20
    linkedin_max_profile_views_per_day: int = 50
    linkedin_min_action_cooldown_hours: int = 2
    linkedin_proxy_list: str = "[]"

    # Observability
    sentry_dsn: str = ""

    # ARQ (async Redis queue)
    arq_redis_url: str = ""

    # LLM fallback and model settings
    llm_fallback_chain: str = "openai"
    llm_openai_model: str = "gpt-4"
    llm_anthropic_model: str = "claude-3-sonnet-20240229"
    llm_groq_model: str = "llama3-8b-8192"
    llm_openai_timeout: int = 30
    llm_anthropic_timeout: int = 45
    llm_groq_timeout: int = 15

    # Notification channels
    slack_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Metrics auth token (optional, protects /metrics endpoint in production)
    metrics_auth_token: str = ""

    # Approval settings
    approval_required_company_size: int = 500

    # Client Telegram bot token
    client_telegram_bot_token: str = ""

    # Auto-approve settings
    auto_approve_enabled: bool = False
    auto_approve_quality_threshold: int = 75
    protected_companies_list: str = "[]"
    auto_approve_max_retries: int = 3

    # Dogfooding settings
    dogfood_enabled: bool = False
    dogfood_sending_domain: str = ""

    # Health monitor settings
    health_check_interval_minutes: int = 5
    health_telegram_alerts: bool = True

    # Backup settings
    backup_dir: str = "/backups"
    backup_retention_days: int = 7
    s3_backup_bucket: str = ""
    s3_backup_endpoint: str = ""
    s3_backup_access_key: str = ""
    s3_backup_secret_key: str = ""

    # Competitive intelligence settings
    competitive_intel_enabled: bool = False
    competitive_intel_competitors: str = "[]"

    # LinkedIn self-healing
    linkedin_self_healing_enabled: bool = True

    # Voice / Twilio settings
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "default"
    voice_max_call_duration: int = 180
    voice_concurrent_calls_limit: int = 5
    voice_calling_hours_start: int = 9
    voice_calling_hours_end: int = 20
    voice_amd_enabled: bool = True


settings = Settings()  # type: ignore[call-arg]
