import base64

import httpx
import structlog
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction as SolanaTransaction
from solders.hash import Hash as SolanaHash
from solders.message import Message

from config import settings

log = structlog.get_logger()

LAMPORTS_PER_SOL = 1_000_000_000


async def _rpc(method: str, params: list) -> dict:
    """Вызывает Solana JSON-RPC API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            settings.SOLANA_RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        resp.raise_for_status()
        return resp.json()


async def get_platform_balance() -> float:
    """Возвращает баланс platform wallet в SOL."""
    try:
        data = await _rpc("getBalance", [settings.PLATFORM_WALLET_ADDRESS])
        lamports = data.get("result", {}).get("value", 0)
        return lamports / LAMPORTS_PER_SOL
    except Exception as e:
        log.error("get_balance_error", error=str(e))
        return 0.0


async def send_sol(to_address: str, amount_sol: float) -> str:
    """
    Отправляет SOL с platform wallet на указанный адрес.
    Возвращает tx hash при успехе, бросает RuntimeError при ошибке.
    """
    lamports = int(amount_sol * LAMPORTS_PER_SOL)

    # Загружаем keypair платформы
    platform_keypair = Keypair.from_base58_string(settings.PLATFORM_WALLET_PRIVATE_KEY)
    to_pubkey = Pubkey.from_string(to_address)

    # Получаем recent blockhash
    bh_data = await _rpc("getLatestBlockhash", [{"commitment": "finalized"}])
    blockhash_str = bh_data["result"]["value"]["blockhash"]
    recent_blockhash = SolanaHash.from_string(blockhash_str)

    # Создаём transfer instruction
    ix = transfer(TransferParams(
        from_pubkey=platform_keypair.pubkey(),
        to_pubkey=to_pubkey,
        lamports=lamports,
    ))

    # Собираем и подписываем транзакцию
    msg = Message([ix], platform_keypair.pubkey())
    tx = SolanaTransaction([platform_keypair], msg, recent_blockhash)

    # Сериализуем и отправляем
    raw_tx = base64.b64encode(bytes(tx)).decode("utf-8")
    result = await _rpc("sendTransaction", [raw_tx, {"encoding": "base64"}])

    if "error" in result:
        err_msg = result["error"].get("message", str(result["error"]))
        log.error("send_sol_failed", to=to_address, amount=amount_sol, error=err_msg)
        raise RuntimeError(f"Solana transfer failed: {err_msg}")

    tx_hash = result.get("result", "")
    log.info("sol_sent", to=to_address, amount_sol=amount_sol, tx_hash=tx_hash)
    return tx_hash


async def verify_deposit_tx(
    tx_hash: str,
    expected_from: str,
    expected_amount_sol: float,
) -> bool:
    """
    Верифицирует Solana транзакцию депозита через JSON-RPC.
    Проверяет: from == expected_from, to == PLATFORM_WALLET, сумма совпадает.
    """
    try:
        data = await _rpc(
            "getTransaction",
            [tx_hash, {"encoding": "json", "maxSupportedTransactionVersion": 0}],
        )
        result = data.get("result")
        if not result:
            log.warning("tx_not_found", tx_hash=tx_hash)
            return False

        meta = result.get("meta", {})
        if meta.get("err") is not None:
            log.warning("tx_has_error", tx_hash=tx_hash, err=meta["err"])
            return False

        account_keys = result["transaction"]["message"]["accountKeys"]
        pre_balances = meta["preBalances"]
        post_balances = meta["postBalances"]

        platform_wallet = settings.PLATFORM_WALLET_ADDRESS

        # Индексы отправителя и получателя
        platform_idx = next((i for i, k in enumerate(account_keys) if k == platform_wallet), None)
        sender_idx = next((i for i, k in enumerate(account_keys) if k == expected_from), None)

        if platform_idx is None or sender_idx is None:
            log.warning("tx_accounts_not_found", tx_hash=tx_hash)
            return False

        # Сколько lamports получил platform wallet
        received_lamports = post_balances[platform_idx] - pre_balances[platform_idx]
        expected_lamports = int(expected_amount_sol * LAMPORTS_PER_SOL)

        if abs(received_lamports - expected_lamports) > 1000:  # допуск 1000 lamports
            log.warning(
                "tx_amount_mismatch",
                expected=expected_amount_sol,
                received=received_lamports / LAMPORTS_PER_SOL,
            )
            return False

        log.info("tx_verified", tx_hash=tx_hash, amount_sol=received_lamports / LAMPORTS_PER_SOL)
        return True

    except Exception as e:
        log.error("tx_verification_error", tx_hash=tx_hash, error=str(e))
        return False
