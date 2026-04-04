"""
Обёртка над Anchor инструкциями программы agent_escrow.
Использует solders для построения транзакций напрямую.
"""
import base64
import hashlib
import struct
from uuid import UUID

import base58
import httpx
import structlog
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.transaction import Transaction

from config import settings

log = structlog.get_logger(__name__)


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def execution_id_to_bytes(execution_id: str) -> bytes:
    """Конвертирует UUID string в 16 байт."""
    try:
        return UUID(execution_id).bytes
    except ValueError as e:
        raise ValueError(f"Invalid UUID: {execution_id}") from e


def get_execution_pda(execution_id: str, program_id: str) -> tuple[str, int]:
    """
    Вычисляет PDA для ExecutionAccount.
    Seeds: [b"execution", execution_id_bytes]
    Возвращает (base58_address, bump).
    """
    exec_bytes = execution_id_to_bytes(execution_id)
    program_pubkey = Pubkey.from_string(program_id)
    pda, bump = Pubkey.find_program_address(
        [b"execution", exec_bytes],
        program_pubkey,
    )
    return str(pda), bump


def get_agent_pda(owner_address: str, slug: str, program_id: str) -> tuple[str, int]:
    """
    Вычисляет PDA для AgentAccount.
    Seeds: [b"agent", owner_pubkey, slug_bytes]
    Возвращает (base58_address, bump).

    Если slug слишком длинный для PDA (> 32 байт), усекаем до 32.
    Перехватываем PanicException — при невозможности найти valid bump.
    """
    slug_bytes = slug.encode()[:32]  # Solana PDA seed max 32 bytes
    owner_pubkey = Pubkey.from_string(owner_address)
    program_pubkey = Pubkey.from_string(program_id)
    try:
        pda, bump = Pubkey.find_program_address(
            [b"agent", bytes(owner_pubkey), slug_bytes],
            program_pubkey,
        )
        return str(pda), bump
    except Exception as e:
        raise ValueError(f"Cannot derive PDA for slug '{slug}': {e}") from e


def _discriminator(instruction_name: str) -> bytes:
    """Вычисляет Anchor discriminator для инструкции (sha256("global:<name>")[:8])."""
    return hashlib.sha256(f"global:{instruction_name}".encode()).digest()[:8]


def _get_platform_keypair() -> Keypair:
    """Загружает platform keypair из настроек."""
    private_key_bytes = base58.b58decode(settings.PLATFORM_WALLET_PRIVATE_KEY)
    return Keypair.from_bytes(private_key_bytes)


async def _get_recent_blockhash() -> str:
    """Получает свежий blockhash от Solana RPC."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            settings.SOLANA_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "confirmed"}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["value"]["blockhash"]


async def _send_transaction_with_retry(
    build_tx_fn,
    max_retries: int = 3,
) -> str:
    """
    Строит и отправляет транзакцию с retry при BlockhashNotFound.
    build_tx_fn(blockhash: str) -> Transaction
    """
    import asyncio as _asyncio

    for attempt in range(max_retries):
        try:
            blockhash = await _get_recent_blockhash()
            tx = build_tx_fn(blockhash)
            tx_bytes = base64.b64encode(bytes(tx)).decode()

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    settings.SOLANA_RPC_URL,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [
                            tx_bytes,
                            {
                                "encoding": "base64",
                                "skipPreflight": True,  # обходим simulation lag на devnet
                                "preflightCommitment": "processed",
                            },
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    err_msg = str(data["error"])
                    if attempt < max_retries - 1:
                        log.warning("send_tx_retry", attempt=attempt + 1, error=err_msg[:100])
                        await _asyncio.sleep(1.5)
                        continue
                    raise RuntimeError(f"Solana RPC error: {data['error']}")
                return data["result"]  # transaction signature
        except RuntimeError:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                await _asyncio.sleep(1.0)
                continue
            raise

    raise RuntimeError("Max retries exceeded sending Solana transaction")


async def _send_transaction(tx: Transaction) -> str:
    """Отправляет подписанную транзакцию и возвращает tx signature (legacy)."""
    tx_bytes = base64.b64encode(bytes(tx)).decode()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            settings.SOLANA_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [tx_bytes, {"encoding": "base64", "skipPreflight": False}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Solana RPC error: {data['error']}")
        return data["result"]  # transaction signature


# ─── On-chain инструкции ──────────────────────────────────────────────────────

async def initiate_execution_onchain(
    execution_id: str,
    agent_pda: str,
    caller_address: str,
) -> str:
    """
    Вызывает initiate_execution в Anchor программе.
    Platform подписывает как proxy за caller (backend не имеет ключа пользователя).
    Адрес caller_address сохраняется в ExecutionAccount для маршрутизации refund.
    Возвращает tx signature.
    """
    program_id = settings.ANCHOR_PROGRAM_ID
    execution_pda, _ = get_execution_pda(execution_id, program_id)
    platform_kp = _get_platform_keypair()

    # Данные: discriminator + execution_id (16 bytes)
    exec_bytes = execution_id_to_bytes(execution_id)
    ix_data = _discriminator("initiate_execution") + exec_bytes

    # Anchor InitiateExecution accounts order: execution_account, agent_account, caller, platform, system_program
    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(execution_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(agent_pda), is_signer=False, is_writable=False),
        AccountMeta(pubkey=Pubkey.from_string(caller_address), is_signer=False, is_writable=False),  # caller (UncheckedAccount)
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=True, is_writable=True),  # platform (Signer + payer)
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    def build_tx(blockhash: str) -> Transaction:
        return Transaction.new_signed_with_payer(
            instructions=[instruction],
            payer=platform_kp.pubkey(),
            signing_keypairs=[platform_kp],
            recent_blockhash=Hash.from_string(blockhash),
        )

    sig = await _send_transaction_with_retry(build_tx)
    log.info("initiate_execution_tx", sig=sig, execution_id=execution_id)
    return sig


async def complete_execution_onchain(
    execution_id: str,
    agent_pda: str,
    agent_owner_address: str,
    ai_quality_score: int,
) -> str:
    """
    Вызывает complete_execution в Anchor программе.
    Подписывается platform keypair (authority программы).
    90% SOL → agent owner, 10% → platform.
    Возвращает tx signature.
    """
    program_id = settings.ANCHOR_PROGRAM_ID
    execution_pda, _ = get_execution_pda(execution_id, program_id)
    platform_kp = _get_platform_keypair()

    # Данные: discriminator + ai_quality_score (u8, 1 byte)
    ix_data = _discriminator("complete_execution") + struct.pack("<B", ai_quality_score)

    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(execution_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(agent_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(agent_owner_address), is_signer=False, is_writable=True),
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=False, is_writable=True),
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=True, is_writable=False),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    def build_tx(blockhash: str) -> Transaction:
        return Transaction.new_signed_with_payer(
            instructions=[instruction],
            payer=platform_kp.pubkey(),
            signing_keypairs=[platform_kp],
            recent_blockhash=Hash.from_string(blockhash),
        )

    sig = await _send_transaction_with_retry(build_tx)
    log.info("complete_execution_tx", sig=sig, score=ai_quality_score, execution_id=execution_id)
    return sig


async def refund_execution_onchain(
    execution_id: str,
    caller_address: str,
) -> str:
    """
    Вызывает refund_execution в Anchor программе.
    100% SOL возвращается caller.
    Подписывается platform keypair.
    Возвращает tx signature.
    """
    program_id = settings.ANCHOR_PROGRAM_ID
    execution_pda, _ = get_execution_pda(execution_id, program_id)
    platform_kp = _get_platform_keypair()

    ix_data = _discriminator("refund_execution")

    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(execution_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(caller_address), is_signer=False, is_writable=True),
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=True, is_writable=False),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    def build_tx(blockhash: str) -> Transaction:
        return Transaction.new_signed_with_payer(
            instructions=[instruction],
            payer=platform_kp.pubkey(),
            signing_keypairs=[platform_kp],
            recent_blockhash=Hash.from_string(blockhash),
        )

    sig = await _send_transaction_with_retry(build_tx)
    log.info("refund_execution_tx", sig=sig, execution_id=execution_id)
    return sig


async def register_agent_onchain(
    owner_address: str,
    slug: str,
    price_per_call_lamports: int,
) -> tuple[str, str]:
    """
    Вызывает register_agent в Anchor программе от имени platform (proxy).
    Platform используется как owner для PDA и как signer — позволяет работать
    без приватного ключа реального owner'а (demo/backend-driven flow).
    В production owner подписывает через Phantom frontend.
    Если ANCHOR_PROGRAM_ID не задан — пропускает (graceful degradation).
    Возвращает (agent_pda_address, tx_signature).
    """
    program_id = settings.ANCHOR_PROGRAM_ID
    if not program_id:
        log.warning("ANCHOR_PROGRAM_ID not set — skipping on-chain registration")
        return "", ""

    platform_kp = _get_platform_keypair()

    # PDA использует platform pubkey как owner — platform подписывает всё
    platform_owner = str(platform_kp.pubkey())
    agent_pda, _ = get_agent_pda(platform_owner, slug, program_id)

    # Данные: discriminator + slug (borsh string: 4 bytes len LE + bytes) + price (u64 LE)
    # Используем оригинальный slug для on-chain данных, но PDA уже посчитана с усечённым
    slug_bytes = slug.encode()
    ix_data = (
        _discriminator("register_agent")
        + struct.pack("<I", len(slug_bytes))
        + slug_bytes
        + struct.pack("<Q", price_per_call_lamports)
    )

    # Anchor RegisterAgent accounts order: agent_account, owner, platform, system_program
    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(agent_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=False, is_writable=False),  # owner (UncheckedAccount)
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=True, is_writable=True),    # platform (Signer + payer)
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    def build_tx(blockhash: str) -> Transaction:
        return Transaction.new_signed_with_payer(
            instructions=[instruction],
            payer=platform_kp.pubkey(),
            signing_keypairs=[platform_kp],
            recent_blockhash=Hash.from_string(blockhash),
        )

    sig = await _send_transaction_with_retry(build_tx)
    log.info("register_agent_tx", sig=sig, pda=agent_pda, slug=slug)
    return agent_pda, sig


async def update_reputation_onchain(
    agent_pda: str,
    new_score_contribution: int,
) -> str:
    """
    Вызывает update_reputation в Anchor программе.
    new_score_contribution: 0–10000 (score * 100, масштаб reputation_score).
    Доступно только после редеплоя контракта с новой инструкцией update_reputation.
    Возвращает tx signature.
    """
    program_id = settings.ANCHOR_PROGRAM_ID
    if not program_id:
        return ""

    platform_kp = _get_platform_keypair()

    # Данные: discriminator + new_score_contribution (u32 LE)
    ix_data = _discriminator("update_reputation") + struct.pack("<I", new_score_contribution)

    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(agent_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=platform_kp.pubkey(), is_signer=True, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    def build_tx(blockhash: str) -> Transaction:
        return Transaction.new_signed_with_payer(
            instructions=[instruction],
            payer=platform_kp.pubkey(),
            signing_keypairs=[platform_kp],
            recent_blockhash=Hash.from_string(blockhash),
        )

    sig = await _send_transaction_with_retry(build_tx)
    log.info("update_reputation_tx", sig=sig, pda=agent_pda, score=new_score_contribution)
    return sig
