from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    simli_api_key: str = ""
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    minute_cost_coins: int = 10
    billing_interval_seconds: int = 60
    cors_origins: list[str] = ["*"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
