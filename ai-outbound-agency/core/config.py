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


settings = Settings()  # type: ignore[call-arg]
