import httpx
import structlog

from config import settings
from database import engine, Base
import models  # noqa: F401 — импортируем все модели чтобы Base их видел

log = structlog.get_logger()

SUPABASE_STORAGE_URL = f"{settings.SUPABASE_URL}/storage/v1"
BUCKET = "agent-bundles"


async def ensure_storage_bucket() -> None:
    """
    Создаёт bucket agent-bundles в Supabase Storage если он не существует.
    Вызывается при старте приложения в lifespan.
    409 = bucket уже существует — это нормально, не падаем.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_STORAGE_URL}/bucket",
            headers={
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "id": BUCKET,
                "name": BUCKET,
                "public": True,
                "file_size_limit": settings.MAX_AGENT_BUNDLE_SIZE_MB * 1024 * 1024,
                "allowed_mime_types": ["application/zip", "application/octet-stream"],
            },
        )
        # Supabase Storage возвращает HTTP 400 с {"statusCode":"409"} если bucket уже существует
        already_exists = resp.status_code == 409 or (
            resp.status_code == 400 and "409" in resp.text
        )
        if resp.status_code not in (200, 201) and not already_exists:
            raise RuntimeError(
                f"Не удалось создать bucket '{BUCKET}': {resp.status_code} {resp.text}"
            )

    log.info("storage_bucket_ready", bucket=BUCKET)


async def ensure_tables() -> None:
    """
    Создаёт новые таблицы и добавляет новые колонки если их нет.
    Безопасно — не трогает существующие данные.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Добавляем новые колонки (ADD COLUMN IF NOT EXISTS — идемпотентно)
        new_columns = [
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS assistant_agent_id UUID",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS assistant_name VARCHAR(50)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS assistant_emoji VARCHAR(10)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS assistant_provider VARCHAR(20)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS assistant_api_key_enc TEXT",
        ]
        from sqlalchemy import text
        for sql in new_columns:
            await conn.execute(text(sql))
    log.info("db_tables_ready")
