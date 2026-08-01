import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List

logger = logging.getLogger(__name__)

# Valores placeholder que NUNCA deben usarse fuera de desarrollo.
INSECURE_SECRETS = {
    "",
    "change-me",
    "changeme",
    "cambiar-esto-por-otra-clave-segura",
    "secret",
    "test",
}

# Placeholders que estuvieron versionados en docker-compose.yml. Son publicos,
# pero no bloquean el arranque para no tumbar un deploy ya en marcha: se avisa
# con nivel CRITICAL en cada arranque hasta que se roten.
PUBLIC_PLACEHOLDER_SECRETS = {
    "cambiar-en-easypanel-settings",
    "cambiar-en-easypanel",
}


class Settings(BaseSettings):
    # App
    app_name: str = "APU Marketplace"
    # Fail-closed: si APP_ENV no esta definido asumimos produccion, para que un
    # deploy mal configurado no exponga /api/docs ni relaje otras defensas.
    app_env: str = "production"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me"
    app_url: str = "http://localhost:8000"
    cors_origins: List[str] = ["http://localhost:8000"]

    # Proxies de confianza: solo se leen cabeceras X-Forwarded-For /
    # CF-Connecting-IP cuando la conexion viene de una de estas redes.
    # Vacio = no confiar en ninguna cabecera (usar IP del socket).
    # Ej: TRUSTED_PROXIES=["10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"]
    trusted_proxies: List[str] = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"]

    # Database
    database_url: str = "postgresql+asyncpg://apu_mkt:apu_mkt_dev@localhost:5432/apu_marketplace"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120
    jwt_refresh_token_expire_days: int = 30

    # Admin
    admin_api_key: str = ""
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Super Admin"

    # AI
    ai_provider: str = "openrouter"
    ai_api_key: str = ""
    ai_model: str = ""
    anthropic_api_key: str = ""  # Fallback: if set, adds Anthropic as extra provider

    # Embeddings (busqueda semantica)
    embedding_provider: str = "openai"          # openai
    embedding_api_key: str = ""                 # OPENAI_API_KEY (o el que corresponda)
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 1536

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

    # Web Push (VAPID) — 5.5
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@localhost"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _fix_database_url(self):
        """Acepta cualquier formato de URL de PostgreSQL y lo convierte a asyncpg.

        EasyPanel, Supabase, Railway, etc. dan URLs como:
          postgres://user:pass@host:5432/db
          postgresql://user:pass@host:5432/db
        SQLAlchemy async necesita:
          postgresql+asyncpg://user:pass@host:5432/db
        """
        url = self.database_url
        if url.startswith("postgres://"):
            self.database_url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            self.database_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self

    @model_validator(mode="after")
    def _enforce_secrets(self):
        """Impide arrancar en produccion con secretos placeholder.

        Un JWT_SECRET_KEY conocido permite a cualquiera firmar un token de
        admin, por lo que en produccion es un fallo de arranque, no un aviso.
        """
        if self.app_env == "development":
            if self.jwt_secret_key.strip().lower() in INSECURE_SECRETS:
                logger.warning(
                    "JWT_SECRET_KEY usa el valor por defecto: solo valido en desarrollo."
                )
            return self

        weak = [
            name
            for name, value in (
                ("JWT_SECRET_KEY", self.jwt_secret_key),
                ("APP_SECRET_KEY", self.app_secret_key),
            )
            if value.strip().lower() in INSECURE_SECRETS
        ]
        if weak:
            raise ValueError(
                f"Secretos inseguros en APP_ENV={self.app_env}: {', '.join(weak)}. "
                "Genera valores unicos (p.ej. `python -c \"import secrets;"
                "print(secrets.token_urlsafe(48))\"`) antes de desplegar."
            )
        # Estos valores estuvieron versionados en docker-compose.yml, asi que
        # son publicos. No bloquean el arranque para no tumbar un despliegue en
        # curso, pero hay que rotarlos: quien los conozca puede firmar un JWT
        # de admin.
        for name, value in (
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("APP_SECRET_KEY", self.app_secret_key),
        ):
            if value.strip().lower() in PUBLIC_PLACEHOLDER_SECRETS:
                logger.critical(
                    "%s usa un valor placeholder que estuvo publicado en el repo. "
                    "ROTALO YA: cualquiera con acceso al repo puede firmar tokens de admin.",
                    name,
                )

        if len(self.jwt_secret_key) < 32:
            logger.warning(
                "JWT_SECRET_KEY tiene menos de 32 caracteres; usa al menos 48 bytes de entropia."
            )
        return self

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "")


settings = Settings()
