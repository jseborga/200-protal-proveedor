from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    app_name: str = "APU Marketplace"
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me"
    app_url: str = "http://localhost:8000"
    cors_origins: List[str] = ["http://localhost:8000"]

    # Database
    database_url: str = "postgresql+asyncpg://apu_mkt:apu_mkt_dev@localhost:5432/apu_marketplace"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    jwt_refresh_token_expire_days: int = 30

    # Admin
    admin_api_key: str = ""

    # AI
    ai_provider: str = "openrouter"
    ai_api_key: str = ""
    ai_model: str = ""

    # WhatsApp (Evolution API)
    evolution_api_url: str = "http://localhost:8080"
    evolution_api_key: str = ""
    evolution_instance_name: str = "apu-marketplace"

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@localhost"
    smtp_tls: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "")


settings = Settings()
