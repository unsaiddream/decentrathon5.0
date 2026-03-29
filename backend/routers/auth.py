import uuid
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth_middleware import get_current_user
from models.user import User
from schemas.auth import TokenResponse, WalletLoginRequest
from schemas.user import UserOut
from services.solana_auth import create_access_token, verify_solana_signature

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
log = structlog.get_logger()

TIMESTAMP_TTL = 300

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


# ─── Wallet Login ──────────────────────────────────────────────────────────────

@router.post("/wallet-login", response_model=TokenResponse)
async def wallet_login(
    body: WalletLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Логин через Solana кошелёк (Phantom)."""
    now = datetime.now(timezone.utc).timestamp()
    if abs(now - body.timestamp) > TIMESTAMP_TTL:
        raise HTTPException(status_code=400, detail="Timestamp устарел, повторите вход")

    if not verify_solana_signature(body.wallet_address, body.message, body.signature):
        raise HTTPException(status_code=401, detail="Невалидная подпись кошелька")

    result = await db.execute(
        select(User).where(User.wallet_address == body.wallet_address)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(wallet_address=body.wallet_address)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        log.info("user_registered", wallet=body.wallet_address)
    else:
        log.info("user_login", wallet=body.wallet_address, user_id=str(user.id))

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


# ─── GitHub OAuth ──────────────────────────────────────────────────────────────

@router.get("/github")
async def github_login(request: Request):
    """Redirect user to GitHub OAuth authorization page."""
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    # Determine callback URL from the request origin
    callback_url = f"{request.base_url}api/v1/auth/github/callback"

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": callback_url,
        "scope": "read:user user:email",
    }
    url = f"{GITHUB_AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    return RedirectResponse(url=url)


@router.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    GitHub OAuth callback.
    Exchanges code for token, fetches user profile, creates/updates user, returns JWT via redirect.
    """
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    # 1. Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        error = token_data.get("error_description", token_data.get("error", "Unknown"))
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")

    # 2. Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch GitHub profile")

    gh = user_resp.json()
    github_id = gh["id"]
    github_username = gh.get("login", "")
    email = gh.get("email")
    avatar_url = gh.get("avatar_url")

    # 3. Find or create user by github_id
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if not user:
        # Generate a pseudo wallet address for GitHub users (not a real Solana key)
        pseudo_wallet = f"gh_{github_id}_{uuid.uuid4().hex[:8]}"

        user = User(
            wallet_address=pseudo_wallet,
            username=github_username,
            email=email,
            github_id=github_id,
            github_username=github_username,
            avatar_url=avatar_url,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        log.info("user_registered_github", github_id=github_id, username=github_username)
    else:
        # Update profile info
        user.github_username = github_username
        user.avatar_url = avatar_url
        if email:
            user.email = email
        await db.commit()
        await db.refresh(user)
        log.info("user_login_github", github_id=github_id, username=github_username)

    # 4. Issue JWT and redirect to frontend with token
    jwt_token = create_access_token(str(user.id))

    # Redirect to frontend with token in URL fragment (not visible to server in subsequent requests)
    redirect_url = f"/ui/auth-callback.html#token={jwt_token}&wallet={user.wallet_address}&username={github_username}&avatar={avatar_url or ''}"
    return RedirectResponse(url=redirect_url)


# ─── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Возвращает профиль текущего авторизованного пользователя."""
    return current_user
