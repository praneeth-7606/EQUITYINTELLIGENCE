import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # LLM API Keys
    xai_api_key: Optional[str] = None
    xai_api_base: str = "https://api.x.ai/v1"
    xai_model: str = "grok-2-1212"
    gemini_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    mistral_api_base: str = "https://api.mistral.ai/v1"
    mistral_model: str = "mistral-large-latest"
    groq_api_key: Optional[str] = None

    # Application Settings
    port: int = 8000
    host: str = "0.0.0.0"
    log_level: str = "info"
    cache_dir: str = ".cache"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "stock_intelligence"

    # JWT Authentication
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_SECRET_32_CHARS"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

settings = Settings()

# Ensure cache directory exists
os.makedirs(settings.cache_dir, exist_ok=True)
