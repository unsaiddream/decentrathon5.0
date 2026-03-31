import io
import json
import re
import zipfile
from decimal import Decimal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth_middleware import get_current_user
from models.agent import Agent
from models.user import User
from schemas.agent import AgentOut, AgentUpdate, AgentListResponse
from schemas.manifest import AgentManifest
from services.storage_service import upload_bundle, delete_bundle
from services.cache_service import cache_get, cache_set, cache_invalidate

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
log = structlog.get_logger()


def _slugify(text: str) -> str:
    """Превращает строку в kebab-case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def _make_slug(owner: User, agent_name: str) -> str:
    """
    Генерирует уникальный slug вида: username/agent-name
    Если username не задан — используем первые 8 символов wallet address.
    """
    prefix = owner.username or owner.wallet_address[:8].lower()
    return f"{prefix}/{_slugify(agent_name)}"


def _extract_manifest(zip_bytes: bytes) -> dict:
    """Извлекает и парсит manifest.json из zip-архива."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            # Ищем manifest.json в корне или в первой директории
            manifest_path = next(
                (n for n in names if n == "manifest.json" or n.endswith("/manifest.json")),
                None,
            )
            if not manifest_path:
                raise HTTPException(status_code=400, detail="manifest.json не найден в zip-архиве")
            with zf.open(manifest_path) as f:
                return json.load(f)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Загруженный файл не является валидным zip-архивом")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="manifest.json содержит невалидный JSON")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_github_url(url: str) -> tuple[str, str, str]:
    """
    Парсит GitHub URL и возвращает (owner, repo, branch).
    Поддерживает форматы:
      https://github.com/owner/repo
      https://github.com/owner/repo/tree/branch
      https://github.com/owner/repo.git
    """
    url = url.strip().rstrip("/")
    # Убираем .git суффикс
    url = re.sub(r"\.git$", "", url)

    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+))?",
        url,
    )
    if not m:
        raise HTTPException(
            status_code=400,
            detail="Неверный GitHub URL. Ожидается: https://github.com/owner/repo",
        )

    owner, repo, branch = m.group(1), m.group(2), m.group(3) or "main"
    return owner, repo, branch


async def _download_github_zip(owner: str, repo: str, branch: str) -> bytes:
    """
    Скачивает репозиторий с GitHub как zip через API.
    GitHub zipball содержит все файлы в подпапке owner-repo-sha/.
    Мы перепаковываем zip, убирая этот префикс.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "HiveMind/1.0"}

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        resp = await client.get(api_url, headers=headers)

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Репозиторий github.com/{owner}/{repo} не найден или приватный",
        )
    if resp.status_code == 403:
        raise HTTPException(status_code=429, detail="GitHub rate limit превышен. Попробуйте позже.")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub вернул ошибку {resp.status_code}",
        )

    raw = resp.content
    max_bytes = settings.MAX_AGENT_BUNDLE_SIZE_MB * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Репозиторий превышает {settings.MAX_AGENT_BUNDLE_SIZE_MB}MB",
        )

    # GitHub кладёт файлы в owner-repo-sha/file.py — убираем этот префикс
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        # Определяем общий префикс (первая папка)
        prefix = ""
        for name in src.namelist():
            if "/" in name:
                prefix = name.split("/")[0] + "/"
                break

        for item in src.infolist():
            # Убираем префикс
            new_name = item.filename[len(prefix):] if prefix and item.filename.startswith(prefix) else item.filename
            if not new_name or new_name.endswith("/"):
                continue  # пропускаем директории
            data = src.read(item.filename)
            dst.writestr(new_name, data)

    return buf.getvalue()


class GithubImportRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    manifest_override: dict | None = None


# ─── Upsert helper ────────────────────────────────────────────────────────────

async def _upsert_agent(
    zip_bytes: bytes,
    manifest: AgentManifest,
    manifest_dict: dict,
    current_user: User,
    db: AsyncSession,
) -> Agent:
    """
    Создаёт нового агента или обновляет существующего (если владелец тот же).
    Возвращает Agent.
    """
    slug = _make_slug(current_user, manifest.name)

    # Загружаем бандл в Storage (x-upsert: true — перезаписывает)
    bundle_url = await upload_bundle(zip_bytes, current_user.wallet_address, slug)

    # Проверяем существует ли агент
    result = await db.execute(select(Agent).where(Agent.slug == slug))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail=f"Агент '{slug}' принадлежит другому пользователю")
        # Обновляем существующий
        existing.description = manifest.description or existing.description
        existing.manifest = manifest_dict
        existing.bundle_url = bundle_url
        existing.price_per_call = Decimal(str(manifest.price_per_call))
        existing.category = manifest.category or existing.category
        existing.tags = manifest.tags or existing.tags
        await db.commit()
        await db.refresh(existing)
        log.info("agent_updated", slug=slug)
        return existing

    # Создаём нового
    agent = Agent(
        owner_id=current_user.id,
        name=manifest.name,
        slug=slug,
        description=manifest.description or None,
        manifest=manifest_dict,
        bundle_url=bundle_url,
        price_per_call=Decimal(str(manifest.price_per_call)),
        category=manifest.category or None,
        tags=manifest.tags or None,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    log.info("agent_created", slug=slug, owner=current_user.wallet_address)

    # Регистрируем агента on-chain (graceful — не блокирует если ANCHOR_PROGRAM_ID не задан)
    if current_user.wallet_address and settings.ANCHOR_PROGRAM_ID:
        try:
            from decimal import Decimal
            from services.onchain_billing import register_agent_onchain
            price_lamports = int(Decimal(str(agent.price_per_call)) * 1_000_000_000)
            agent_pda, register_tx = await register_agent_onchain(
                owner_address=current_user.wallet_address,
                slug=agent.slug,
                price_per_call_lamports=price_lamports,
            )
            if agent_pda:
                agent.on_chain_address = agent_pda
                agent.register_tx_hash = register_tx
                await db.commit()
                log.info("agent_registered_onchain", slug=agent.slug, pda=agent_pda)
        except Exception as e:
            log.error("onchain_registration_failed", slug=agent.slug, error=str(e))

    return agent


# ─── POST /api/v1/agents ──────────────────────────────────────────────────────
@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    bundle: UploadFile = File(..., description="zip-архив с agent.py и manifest.json"),
    manifest_override: str | None = Form(default=None, description="JSON для переопределения полей манифеста"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Загружает нового агента или обновляет существующего (если slug совпадает и владелец тот же).
    """
    max_bytes = settings.MAX_AGENT_BUNDLE_SIZE_MB * 1024 * 1024
    file_bytes = await bundle.read()
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Размер бандла превышает {settings.MAX_AGENT_BUNDLE_SIZE_MB}MB")

    raw_manifest = _extract_manifest(file_bytes)

    if manifest_override:
        try:
            raw_manifest.update(json.loads(manifest_override))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="manifest_override содержит невалидный JSON")

    try:
        manifest = AgentManifest(**raw_manifest)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Невалидный manifest: {e}")

    agent = await _upsert_agent(file_bytes, manifest, manifest.model_dump(), current_user, db)
    cache_invalidate("agents:")
    return agent


# ─── POST /api/v1/agents/import-github ───────────────────────────────────────
@router.post("/import-github", response_model=AgentOut, status_code=201)
async def import_from_github(
    body: GithubImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Импортирует агента из публичного GitHub репозитория.
    Если агент с таким slug уже существует и принадлежит текущему пользователю — обновляет его.
    """
    owner, repo, branch = _parse_github_url(body.repo_url)
    if body.branch and body.branch != "main":
        branch = body.branch

    log.info("github_import_start", owner=owner, repo=repo, branch=branch)

    zip_bytes = await _download_github_zip(owner, repo, branch)
    raw_manifest = _extract_manifest(zip_bytes)

    if body.manifest_override:
        raw_manifest.update(body.manifest_override)

    raw_manifest.setdefault("github_repo", f"https://github.com/{owner}/{repo}")

    try:
        manifest = AgentManifest(**raw_manifest)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Невалидный manifest: {e}")

    manifest_dict = {**manifest.model_dump(), "github_repo": f"https://github.com/{owner}/{repo}"}
    agent = await _upsert_agent(zip_bytes, manifest, manifest_dict, current_user, db)
    cache_invalidate("agents:")
    return agent


# ─── GET /api/v1/agents/my ─────────────────────────────────────────────────────
# IMPORTANT: must be registered before /{slug:path} to avoid being caught by it
@router.get("/my", response_model=AgentListResponse)
async def list_my_agents(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Все агенты текущего пользователя (включая inactive/private)."""
    query = select(Agent).where(Agent.owner_id == current_user.id).order_by(Agent.created_at.desc())
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()
    result = await db.execute(query.limit(limit))
    agents = result.scalars().all()
    return AgentListResponse(agents=list(agents), total=total, page=1, limit=limit)


# ─── GET /api/v1/agents ───────────────────────────────────────────────────────
@router.get("", response_model=AgentListResponse)
async def list_agents(
    search: str | None = Query(default=None, description="Поиск по имени и описанию"),
    category: str | None = Query(default=None),
    sort: str = Query(default="popular", enum=["popular", "recent", "price_asc", "price_desc"]),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Публичный листинг агентов с поиском, фильтрацией и сортировкой."""
    # Проверяем кэш (5 мин TTL)
    cache_key = f"agents:list:{search}:{category}:{sort}:{page}:{limit}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    query = select(Agent).where(Agent.is_public == True, Agent.is_active == True)  # noqa: E712

    if search:
        query = query.where(
            or_(
                Agent.name.ilike(f"%{search}%"),
                Agent.description.ilike(f"%{search}%"),
            )
        )
    if category:
        query = query.where(Agent.category == category)

    # Сортировка
    if sort == "popular":
        query = query.order_by(Agent.call_count.desc(), Agent.rating_avg.desc())
    elif sort == "recent":
        query = query.order_by(Agent.created_at.desc())
    elif sort == "price_asc":
        query = query.order_by(Agent.price_per_call.asc())
    elif sort == "price_desc":
        query = query.order_by(Agent.price_per_call.desc())

    # Подсчёт total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Пагинация
    result = await db.execute(query.offset((page - 1) * limit).limit(limit))
    agents = result.scalars().all()

    response = AgentListResponse(agents=list(agents), total=total, page=page, limit=limit)
    cache_set(cache_key, response, ttl=300)
    return response


# ─── GET /api/v1/agents/{slug} ────────────────────────────────────────────────
@router.get("/{slug:path}", response_model=AgentOut)
async def get_agent(slug: str, db: AsyncSession = Depends(get_db)):
    """Получить агента по slug (формат: username/agent-name)."""
    result = await db.execute(select(Agent).where(Agent.slug == slug))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Агент '{slug}' не найден")
    return agent


# ─── PUT /api/v1/agents/{slug} ────────────────────────────────────────────────
@router.put("/{slug:path}", response_model=AgentOut)
async def update_agent(
    slug: str,
    body: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Обновить описание, цену или статус агента. Только владелец."""
    result = await db.execute(select(Agent).where(Agent.slug == slug))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    if agent.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав на редактирование")

    if body.description is not None:
        agent.description = body.description
    if body.price_per_call is not None:
        agent.price_per_call = body.price_per_call
    if body.is_active is not None:
        agent.is_active = body.is_active
    if body.is_public is not None:
        agent.is_public = body.is_public

    await db.commit()
    await db.refresh(agent)
    cache_invalidate("agents:")
    return agent


# ─── DELETE /api/v1/agents/{slug} ─────────────────────────────────────────────
@router.delete("/{slug:path}", status_code=204)
async def delete_agent(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Удалить агента и его бандл из Storage. Только владелец."""
    result = await db.execute(select(Agent).where(Agent.slug == slug))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    if agent.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав на удаление")

    await delete_bundle(current_user.wallet_address, slug)
    await db.delete(agent)
    await db.commit()
    cache_invalidate("agents:")
    log.info("agent_deleted", slug=slug)
