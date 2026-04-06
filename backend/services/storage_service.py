import httpx
import structlog

from config import settings

log = structlog.get_logger()

STORAGE_URL = f"{settings.SUPABASE_URL}/storage/v1"
BUCKET = "agent-bundles"


async def upload_bundle(file_bytes: bytes, owner_wallet: str, agent_slug: str) -> str:
    """
    Загружает zip-бандл агента в Supabase Storage.
    Путь: {owner_wallet}/{agent_slug}/bundle.zip
    Возвращает публичный URL.
    """
    path = f"{owner_wallet}/{agent_slug}/bundle.zip"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STORAGE_URL}/object/{BUCKET}/{path}",
            headers={
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/zip",
                "x-upsert": "true",  # перезаписать если уже существует
            },
            content=file_bytes,
            timeout=60.0,
        )
        resp.raise_for_status()

    log.info("bundle_uploaded", path=path, size=len(file_bytes))
    return f"{STORAGE_URL}/object/public/{BUCKET}/{path}"


async def delete_bundle(owner_wallet: str, agent_slug: str) -> None:
    """Удаляет бандл при удалении агента."""
    path = f"{owner_wallet}/{agent_slug}/bundle.zip"
    async with httpx.AsyncClient() as client:
        await client.delete(
            f"{STORAGE_URL}/object/{BUCKET}/{path}",
            headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"},
        )
    log.info("bundle_deleted", path=path)


async def download_bundle_by_url(bundle_url: str) -> bytes:
    """Скачивает zip-бандл по прямому URL (public или authenticated)."""
    async with httpx.AsyncClient() as client:
        # Сначала пробуем публичный URL как есть
        resp = await client.get(bundle_url, timeout=60.0)
        if resp.status_code == 200:
            return resp.content

        # Если public URL не сработал — пробуем через service key (private bucket)
        # Убираем /public/ из пути для authenticated доступа
        private_url = bundle_url.replace("/object/public/", "/object/")
        resp = await client.get(
            private_url,
            headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.content


async def download_bundle(owner_wallet: str, agent_slug: str) -> bytes:
    """Скачивает zip-бандл для выполнения агента (legacy — по owner_wallet + slug)."""
    path = f"{owner_wallet}/{agent_slug}/bundle.zip"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STORAGE_URL}/object/{BUCKET}/{path}",
            headers={"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.content
