"""
Скрипт для регистрации всех существующих агентов on-chain.
Запускать из docker: docker compose exec api python scripts/register_agents_onchain.py
"""
import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, '/app/backend')

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from config import settings
from models.agent import Agent
from services.onchain_billing import register_agent_onchain

log = structlog.get_logger()


async def main():
    if not settings.ANCHOR_PROGRAM_ID:
        print("ERROR: ANCHOR_PROGRAM_ID not set")
        return

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.is_active == True,
                Agent.on_chain_address == None,
            )
        )
        agents = result.scalars().all()
        print(f"Found {len(agents)} agents without on-chain address")

        ok = 0
        fail = 0
        for agent in agents:
            try:
                price_lamports = int(Decimal(str(agent.price_per_call)) * 1_000_000_000)
                if price_lamports == 0:
                    price_lamports = 1_000_000  # 0.001 SOL minimum

                agent_pda, register_tx = await register_agent_onchain(
                    owner_address=settings.PLATFORM_WALLET_ADDRESS,
                    slug=agent.slug,
                    price_per_call_lamports=price_lamports,
                )
                if agent_pda:
                    agent.on_chain_address = agent_pda
                    agent.register_tx_hash = register_tx
                    await db.commit()
                    print(f"  ✓ {agent.slug} → PDA: {agent_pda[:20]}... TX: {register_tx[:20]}...")
                    ok += 1
                else:
                    print(f"  ✗ {agent.slug} → empty PDA (program ID not set?)")
                    fail += 1
                # небольшая пауза между транзакциями
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  ✗ {agent.slug} → ERROR: {e}")
                fail += 1

        print(f"\nDone: {ok} registered, {fail} failed")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
