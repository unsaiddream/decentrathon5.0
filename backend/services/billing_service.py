from decimal import Decimal
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent import Agent
from models.transaction import Transaction
from models.user import User
from services.solana_service import send_sol

log = structlog.get_logger()

PLATFORM_FEE_PCT = Decimal("0.10")  # 10%
WITHDRAW_FEE_PCT = Decimal("0.10")  # 10% комиссия на вывод
MIN_WITHDRAW_SOL = Decimal("0.01")  # минимальный вывод


async def charge_for_execution(
    caller: User,
    agent: Agent,
    execution_id: UUID,
    db: AsyncSession,
) -> bool:
    """
    Списывает плату за вызов агента.

    Флоу:
    1. Проверить баланс caller >= price_per_call
    2. Списать с caller
    3. 90% → owner агента
    4. 10% → platform (остаётся как резерв, выводится через payout)
    5. Записать 2 транзакции в БД
    """
    price = agent.price_per_call
    if caller.balance_sol < price:
        raise HTTPException(
            status_code=402,
            detail=f"Недостаточно средств. Нужно {price} SOL, у вас {caller.balance_sol} SOL",
        )

    platform_cut = (price * PLATFORM_FEE_PCT).quantize(Decimal("0.000000001"))
    owner_cut = price - platform_cut

    # Списываем с caller
    caller.balance_sol -= price

    # Начисляем владельцу агента (если это не сам caller)
    owner_result = await db.execute(select(User).where(User.id == agent.owner_id))
    owner = owner_result.scalar_one_or_none()
    if owner and owner.id != caller.id:
        owner.balance_sol += owner_cut

    # Записываем транзакцию call_fee
    tx_fee = Transaction(
        from_user=caller.id,
        to_user=agent.owner_id,
        amount_sol=price,
        type="call_fee",
        execution_id=execution_id,
    )
    # Записываем platform_fee
    tx_platform = Transaction(
        from_user=agent.owner_id,
        to_user=None,  # platform резерв
        amount_sol=platform_cut,
        type="platform_fee",
        execution_id=execution_id,
    )
    db.add(tx_fee)
    db.add(tx_platform)

    log.info(
        "execution_charged",
        caller=str(caller.id),
        agent=agent.slug,
        price=str(price),
        owner_cut=str(owner_cut),
    )
    return True


async def deposit(
    user: User,
    amount_sol: float,
    tx_hash: str,
    db: AsyncSession,
) -> Decimal:
    """Пополняет внутренний баланс пользователя после верификации on-chain tx."""
    amount = Decimal(str(amount_sol))
    user.balance_sol += amount

    tx = Transaction(
        from_user=None,
        to_user=user.id,
        amount_sol=amount,
        type="deposit",
        tx_hash=tx_hash,
    )
    db.add(tx)
    log.info("deposit_credited", user=str(user.id), amount=str(amount))
    return user.balance_sol


async def withdraw(
    user: User,
    amount_sol: float,
    to_wallet: str,
    db: AsyncSession,
) -> dict:
    """
    Выводит SOL с внутреннего баланса на кошелёк пользователя.

    Флоу:
    1. Проверить баланс >= amount
    2. Рассчитать комиссию 10%
    3. Списать полную сумму с баланса
    4. Отправить (amount - комиссия) on-chain
    5. Записать транзакции (payout + withdraw_fee)
    """
    amount = Decimal(str(amount_sol))

    if amount < MIN_WITHDRAW_SOL:
        raise HTTPException(
            status_code=400,
            detail=f"Минимальная сумма вывода: {MIN_WITHDRAW_SOL} SOL",
        )

    if user.balance_sol < amount:
        raise HTTPException(
            status_code=402,
            detail=f"Недостаточно средств. Баланс: {user.balance_sol} SOL, запрошено: {amount} SOL",
        )

    # Комиссия 10%
    fee = (amount * WITHDRAW_FEE_PCT).quantize(Decimal("0.000000001"))
    payout_amount = amount - fee

    if payout_amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма после комиссии слишком мала")

    # Проверяем баланс platform wallet on-chain
    from services.solana_service import get_platform_balance
    platform_bal = await get_platform_balance()
    if platform_bal < float(payout_amount) + 0.001:  # +0.001 на gas fee
        raise HTTPException(
            status_code=503,
            detail=f"Недостаточно средств на кошельке платформы. Доступно: {platform_bal:.4f} SOL. Попробуйте меньшую сумму или обратитесь к администратору.",
        )

    # Списываем с баланса ДО отправки (чтобы не было двойного вывода)
    user.balance_sol -= amount
    await db.flush()

    # Отправляем on-chain
    try:
        tx_hash = await send_sol(to_wallet, float(payout_amount))
    except Exception as e:
        # Откатываем списание при ошибке
        user.balance_sol += amount
        await db.flush()
        log.error("withdraw_failed", user=str(user.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Ошибка отправки SOL: {str(e)[:200]}")

    # Записываем транзакцию вывода
    tx_payout = Transaction(
        from_user=user.id,
        to_user=None,
        amount_sol=payout_amount,
        type="payout",
        tx_hash=tx_hash,
    )
    # Записываем комиссию
    tx_fee = Transaction(
        from_user=user.id,
        to_user=None,
        amount_sol=fee,
        type="withdraw_fee",
    )
    db.add(tx_payout)
    db.add(tx_fee)

    log.info(
        "withdraw_success",
        user=str(user.id),
        amount=str(amount),
        fee=str(fee),
        payout=str(payout_amount),
        to_wallet=to_wallet,
        tx_hash=tx_hash,
    )

    return {
        "tx_hash": tx_hash,
        "amount_sol": str(amount),
        "fee_sol": str(fee),
        "payout_sol": str(payout_amount),
        "new_balance_sol": str(user.balance_sol),
    }
