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


settings = Settings()  # type: ignore[call-arg]
