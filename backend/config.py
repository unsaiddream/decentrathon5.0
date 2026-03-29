import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env лежит в корне проекта, на уровень выше backend/
_ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Supabase ───────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str

    # ─── База данных ────────────────────────────────────────────────
    # Transaction Pooler (порт 6543) — для FastAPI и Celery
    DATABASE_URL: str
    # Прямое подключение (порт 5432) — только для alembic миграций
    DATABASE_DIRECT_URL: str

    # ─── Redis / Celery ─────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ─── Solana ──────────────────────────────────────────────────────
    SOLANA_RPC_URL: str = "https://api.devnet.solana.com"
    PLATFORM_WALLET_ADDRESS: str = ""
    PLATFORM_WALLET_PRIVATE_KEY: str = ""

    # ─── JWT ────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_EXPIRE_HOURS: int = 168
    JWT_ALGORITHM: str = "HS256"

    # ─── GitHub OAuth ─────────────────────────────────────────────────
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # ─── Platform ───────────────────────────────────────────────────
    PLATFORM_FEE_PCT: float = 0.10
    MAX_AGENT_BUNDLE_SIZE_MB: int = 50
    EXECUTION_TIMEOUT_SECONDS: int = 60


settings = Settings()
