from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth_middleware import get_current_user
from models.transaction import Transaction
from models.user import User
from schemas.payment import DepositRequest, WithdrawRequest, TransactionOut, EarningsResponse
from services.billing_service import deposit, withdraw
from services.solana_service import verify_deposit_tx, get_platform_balance

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])
log = structlog.get_logger()


@router.post("/deposit", response_model=dict)
async def make_deposit(
    body: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Пополняет внутренний баланс после отправки SOL на platform wallet.
    Верифицирует транзакцию on-chain перед зачислением.
    """
    # Проверяем что tx_hash ещё не использовался
    existing = await db.execute(
        select(Transaction).where(Transaction.tx_hash == body.tx_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Транзакция уже была использована")

    # Верифицируем on-chain (только если platform wallet задан)
    from config import settings
    if settings.PLATFORM_WALLET_ADDRESS and settings.PLATFORM_WALLET_ADDRESS != "заполнишь_позже":
        ok = await verify_deposit_tx(
            body.tx_hash,
            current_user.wallet_address,
            body.amount_sol,
        )
        if not ok:
            raise HTTPException(status_code=400, detail="Транзакция не прошла верификацию")

    new_balance = await deposit(current_user, body.amount_sol, body.tx_hash, db)
    await db.commit()

    return {"balance_sol": str(new_balance)}


@router.post("/withdraw", response_model=dict)
async def make_withdraw(
    body: WithdrawRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Выводит SOL с внутреннего баланса на указанный кошелёк.
    Комиссия: 10%. Минимум: 0.01 SOL.
    """
    result = await withdraw(current_user, body.amount_sol, body.to_wallet, db)
    await db.commit()
    return result


@router.get("/balance", response_model=dict)
async def get_balance(
    current_user: User = Depends(get_current_user),
):
    """Баланс пользователя."""
    return {
        "balance_sol": str(current_user.balance_sol),
        "wallet_address": current_user.wallet_address,
    }


@router.get("/history", response_model=list[TransactionOut])
async def payment_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История транзакций пользователя."""
    result = await db.execute(
        select(Transaction)
        .where(
            (Transaction.from_user == current_user.id)
            | (Transaction.to_user == current_user.id)
        )
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/earnings", response_model=EarningsResponse)
async def get_earnings(
    period: str = Query(default="30d", enum=["7d", "30d", "all"]),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Сколько заработал владелец агентов за период."""
    query = select(Transaction).where(
        Transaction.to_user == current_user.id,
        Transaction.type == "call_fee",
    )
    if period != "all":
        days = 7 if period == "7d" else 30
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(Transaction.created_at >= since)

    result = await db.execute(query)
    txs = result.scalars().all()
    total = sum(t.amount_sol for t in txs) if txs else Decimal("0")

    return EarningsResponse(total_earned_sol=total, period=period)
