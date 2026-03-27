# Part 3: On-Chain Billing Integration

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the existing off-chain escrow billing with real Anchor smart contract calls. Every agent execution now creates an on-chain ExecutionAccount PDA, locks SOL, then releases or refunds based on the AI quality score.

**Architecture:** `onchain_billing.py` wraps the Anchor program instructions using `solders`. It is called from the Celery `execute_task` after AI evaluation. The existing `billing_service.py` (off-chain) stays intact for deposits/withdrawals — only the per-execution escrow moves on-chain. The DB stores both the off-chain execution ID and the on-chain PDA address + tx hashes.

**Tech Stack:** `solders` (already installed), `anchorpy` for IDL-based instruction building, Alembic for DB migration, FastAPI (existing)

---

## Prerequisites

- Part 1 complete (Anchor program deployed, Program ID in `.env`)
- Part 2 complete (AI coordinator working)
- `ANCHOR_PROGRAM_ID` set in `.env`
- `PLATFORM_WALLET_PRIVATE_KEY` set in `.env`

---

## File Structure

```
backend/
├── services/
│   └── onchain_billing.py          # CREATE — Anchor instruction builders
├── tasks/
│   └── execute_task.py             # MODIFY — call onchain_billing after evaluation
├── routers/
│   └── executions.py               # MODIFY — expose on-chain tx hashes in response
├── models/
│   └── execution.py                # MODIFY — add on_chain_* fields
├── tests/
│   └── test_onchain_billing.py     # CREATE
alembic/
└── versions/
    └── 005_onchain_execution_fields.py  # CREATE — migration
```

---

## Task 1: Add anchorpy and update config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`

- [ ] **Step 1: Add anchorpy to requirements.txt**

Open `backend/requirements.txt` and add:

```
anchorpy>=0.20.0
```

- [ ] **Step 2: Install**

```bash
cd backend && pip install anchorpy>=0.20.0
```

Expected: `Successfully installed anchorpy-X.X.X`

- [ ] **Step 3: Add ANCHOR_PROGRAM_ID to config.py**

Open `backend/config.py`, find the `Settings` class, add:

```python
# Solana Anchor программа
anchor_program_id: str = ""
```

- [ ] **Step 4: Verify**

```bash
cd backend && python -c "from config import settings; print(settings.anchor_program_id)"
```

Expected: prints empty string (or your program ID if .env is set).

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/config.py
git commit -m "feat: add anchorpy dependency and anchor_program_id config"
```

---

## Task 2: Alembic migration — add on-chain fields

**Files:**
- Create: `alembic/versions/005_onchain_execution_fields.py`
- Modify: `backend/models/execution.py`

- [ ] **Step 1: Write failing test for new model fields**

Create `backend/tests/test_models.py`:

```python
import pytest
from models.execution import Execution


def test_execution_model_has_onchain_fields():
    """Модель Execution должна иметь on-chain поля."""
    # Проверяем что атрибуты существуют в модели
    assert hasattr(Execution, "on_chain_execution_id")
    assert hasattr(Execution, "on_chain_tx_hash")
    assert hasattr(Execution, "complete_tx_hash")
    assert hasattr(Execution, "ai_quality_score")
    assert hasattr(Execution, "ai_reasoning")
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_models.py -v 2>&1 | head -15
```

Expected: `AttributeError` or `AssertionError` — fields don't exist.

- [ ] **Step 3: Add fields to Execution model**

Open `backend/models/execution.py`. Add these columns to the `Execution` class (after existing columns):

```python
# On-chain данные (заполняются после взаимодействия со смарт-контрактом)
on_chain_execution_id = Column(String(88), nullable=True)  # Solana PDA address
on_chain_tx_hash = Column(String(88), nullable=True)       # tx инициации escrow
complete_tx_hash = Column(String(88), nullable=True)       # tx завершения/возврата
ai_quality_score = Column(SmallInteger, nullable=True)     # 0-100 от AI координатора
ai_reasoning = Column(Text, nullable=True)                 # объяснение оценки
```

Make sure these imports are at the top of the file:
```python
from sqlalchemy import Column, String, SmallInteger, Text
```

- [ ] **Step 4: Run test — expect pass**

```bash
cd backend && python -m pytest tests/test_models.py -v 2>&1 | grep -E "(PASSED|FAILED)"
```

Expected: PASSED

- [ ] **Step 5: Create Alembic migration**

```bash
cd .. && alembic revision -m "onchain_execution_fields"
```

This creates `alembic/versions/XXXX_onchain_execution_fields.py`. Open it and replace the `upgrade()` and `downgrade()` functions:

```python
def upgrade() -> None:
    op.add_column("executions", sa.Column("on_chain_execution_id", sa.String(88), nullable=True))
    op.add_column("executions", sa.Column("on_chain_tx_hash", sa.String(88), nullable=True))
    op.add_column("executions", sa.Column("complete_tx_hash", sa.String(88), nullable=True))
    op.add_column("executions", sa.Column("ai_quality_score", sa.SmallInteger(), nullable=True))
    op.add_column("executions", sa.Column("ai_reasoning", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("executions", "ai_reasoning")
    op.drop_column("executions", "ai_quality_score")
    op.drop_column("executions", "complete_tx_hash")
    op.drop_column("executions", "on_chain_tx_hash")
    op.drop_column("executions", "on_chain_execution_id")
```

Also add the import at the top of the migration file:
```python
import sqlalchemy as sa
```

- [ ] **Step 6: Apply migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade ... -> XXXX, onchain_execution_fields`

- [ ] **Step 7: Commit**

```bash
git add backend/models/execution.py alembic/versions/ backend/tests/test_models.py
git commit -m "feat: add on-chain fields to Execution model and apply migration"
```

---

## Task 3: Implement onchain_billing.py

**Files:**
- Create: `backend/services/onchain_billing.py`

This service builds and sends Anchor instructions using `solders` directly (without anchorpy's account resolution — we build instructions manually for reliability).

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_onchain_billing.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID


def test_execution_id_to_bytes():
    """UUID string должен корректно конвертироваться в 16-байтовый массив."""
    from services.onchain_billing import execution_id_to_bytes

    exec_id = "550e8400-e29b-41d4-a716-446655440000"
    result = execution_id_to_bytes(exec_id)

    assert len(result) == 16
    assert isinstance(result, bytes)
    assert result == UUID(exec_id).bytes


def test_execution_id_to_bytes_invalid():
    """Невалидный UUID должен поднять ValueError."""
    from services.onchain_billing import execution_id_to_bytes

    with pytest.raises(ValueError):
        execution_id_to_bytes("not-a-uuid")


def test_get_execution_pda():
    """PDA должен вычисляться детерминированно для одного execution_id."""
    from services.onchain_billing import get_execution_pda

    exec_id = "550e8400-e29b-41d4-a716-446655440000"
    program_id = "Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkg476zPFsLnS"

    pda1, bump1 = get_execution_pda(exec_id, program_id)
    pda2, bump2 = get_execution_pda(exec_id, program_id)

    assert pda1 == pda2  # детерминированный
    assert bump1 == bump2
    assert len(pda1) == 44  # base58 Solana pubkey длина


def test_get_agent_pda():
    """AgentAccount PDA должен зависеть от owner + slug."""
    from services.onchain_billing import get_agent_pda

    owner = "So11111111111111111111111111111111111111112"
    slug = "test-user/my-agent"
    program_id = "Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkg476zPFsLnS"

    pda1, _ = get_agent_pda(owner, slug, program_id)
    pda2, _ = get_agent_pda(owner, slug, program_id)

    assert pda1 == pda2
    assert len(pda1) == 44
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_onchain_billing.py -v 2>&1 | head -15
```

Expected: `ImportError` — module doesn't exist.

- [ ] **Step 3: Create services/onchain_billing.py**

```python
# services/onchain_billing.py
"""
Обёртка над Anchor инструкциями программы agent_escrow.
Использует solders для построения транзакций напрямую.
"""
import struct
import logging
from uuid import UUID

from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import Transaction
from solders.instruction import Instruction, AccountMeta
from solders.hash import Hash
from solders.system_program import ID as SYS_PROGRAM_ID
import base58
import httpx

from config import settings

logger = logging.getLogger(__name__)

# ─── Вспомогательные функции ─────────────────────────────────

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
    """
    owner_pubkey = Pubkey.from_string(owner_address)
    program_pubkey = Pubkey.from_string(program_id)
    pda, bump = Pubkey.find_program_address(
        [b"agent", bytes(owner_pubkey), slug.encode()],
        program_pubkey,
    )
    return str(pda), bump


def _get_platform_keypair() -> Keypair:
    """Загружает platform keypair из настроек."""
    private_key_b58 = settings.platform_wallet_private_key
    private_key_bytes = base58.b58decode(private_key_b58)
    return Keypair.from_bytes(private_key_bytes)


async def _get_recent_blockhash() -> str:
    """Получает свежий blockhash от Solana RPC."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            settings.solana_rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "confirmed"}],
            },
        )
        data = resp.json()
        return data["result"]["value"]["blockhash"]


async def _send_transaction(tx: Transaction) -> str:
    """Отправляет подписанную транзакцию и возвращает tx signature."""
    import base64
    tx_bytes = base64.b64encode(bytes(tx)).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            settings.solana_rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [tx_bytes, {"encoding": "base64", "skipPreflight": False}],
            },
        )
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Solana RPC error: {data['error']}")
        return data["result"]  # transaction signature


# ─── Anchor discriminators (sha256("global:<instruction_name>")[:8]) ─────────
# Генерировать командой: anchor idl parse --file programs/agent_escrow/src/lib.rs
# Или вычислить: import hashlib; hashlib.sha256(b"global:initiate_execution").digest()[:8]

def _discriminator(instruction_name: str) -> bytes:
    """Вычисляет Anchor discriminator для инструкции."""
    import hashlib
    return hashlib.sha256(f"global:{instruction_name}".encode()).digest()[:8]


# ─── On-chain инструкции ──────────────────────────────────────

async def initiate_execution_onchain(
    execution_id: str,
    agent_pda: str,
    caller_address: str,
) -> str:
    """
    Вызывает initiate_execution в Anchor программе.
    Подписывает транзакцию от имени caller (требует их подпись — для MVP
    подписываем platform keypair как proxy, реальный флоу через frontend).
    Возвращает tx signature.
    """
    program_id = settings.anchor_program_id
    execution_pda, _ = get_execution_pda(execution_id, program_id)

    platform_kp = _get_platform_keypair()

    # Данные инструкции: discriminator + execution_id (16 bytes)
    exec_bytes = execution_id_to_bytes(execution_id)
    ix_data = _discriminator("initiate_execution") + exec_bytes

    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(execution_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(agent_pda), is_signer=False, is_writable=False),
        AccountMeta(pubkey=Pubkey.from_string(caller_address), is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    blockhash = await _get_recent_blockhash()
    tx = Transaction.new_signed_with_payer(
        instructions=[instruction],
        payer=platform_kp.pubkey(),
        signing_keypairs=[platform_kp],
        recent_blockhash=Hash.from_string(blockhash),
    )

    sig = await _send_transaction(tx)
    logger.info(f"initiate_execution tx: {sig} for execution {execution_id}")
    return sig


async def complete_execution_onchain(
    execution_id: str,
    agent_pda: str,
    agent_owner_address: str,
    ai_quality_score: int,
) -> str:
    """
    Вызывает complete_execution в Anchor программе.
    Подписывается platform keypair.
    Возвращает tx signature.
    """
    program_id = settings.anchor_program_id
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

    blockhash = await _get_recent_blockhash()
    tx = Transaction.new_signed_with_payer(
        instructions=[instruction],
        payer=platform_kp.pubkey(),
        signing_keypairs=[platform_kp],
        recent_blockhash=Hash.from_string(blockhash),
    )

    sig = await _send_transaction(tx)
    logger.info(f"complete_execution tx: {sig}, score={ai_quality_score}, execution={execution_id}")
    return sig


async def refund_execution_onchain(
    execution_id: str,
    caller_address: str,
) -> str:
    """
    Вызывает refund_execution в Anchor программе.
    Подписывается platform keypair.
    Возвращает tx signature.
    """
    program_id = settings.anchor_program_id
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

    blockhash = await _get_recent_blockhash()
    tx = Transaction.new_signed_with_payer(
        instructions=[instruction],
        payer=platform_kp.pubkey(),
        signing_keypairs=[platform_kp],
        recent_blockhash=Hash.from_string(blockhash),
    )

    sig = await _send_transaction(tx)
    logger.info(f"refund_execution tx: {sig}, execution={execution_id}")
    return sig
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_onchain_billing.py -v 2>&1 | grep -E "(PASSED|FAILED)"
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/services/onchain_billing.py backend/tests/test_onchain_billing.py
git commit -m "feat: implement onchain_billing service — Anchor instruction builders"
```

---

## Task 4: Wire on-chain billing into Celery execute_task

**Files:**
- Modify: `backend/tasks/execute_task.py`

- [ ] **Step 1: Write integration test**

Add to `backend/tests/test_execute_task.py`:

```python
@pytest.mark.asyncio
async def test_complete_execution_called_when_quality_high():
    """При score >= threshold должен вызваться complete_execution_onchain."""
    from uuid import uuid4

    execution_id = str(uuid4())

    mock_evaluation = MagicMock()
    mock_evaluation.score = 85
    mock_evaluation.reasoning = "Good"
    mock_evaluation.should_pay = True

    with patch("tasks.execute_task.get_coordinator") as mock_get_coord, \
         patch("tasks.execute_task.run_agent_in_sandbox") as mock_sandbox, \
         patch("tasks.execute_task.complete_execution_onchain") as mock_complete, \
         patch("tasks.execute_task.refund_execution_onchain") as mock_refund:

        mock_coordinator = AsyncMock()
        mock_get_coord.return_value = mock_coordinator
        mock_coordinator.evaluate_output = AsyncMock(return_value=mock_evaluation)
        mock_sandbox.return_value = {"result": "output"}
        mock_complete.return_value = "fake_tx_hash"
        mock_refund.return_value = "fake_tx_hash"

        from tasks.execute_task import run_execution_with_evaluation

        result = await run_execution_with_evaluation(
            execution_id=execution_id,
            agent_slug="@user/test",
            agent_description="Test",
            input_data={"x": 1},
            agent_pda="So11111111111111111111111111111111111111112",
            agent_owner_address="So11111111111111111111111111111111111111112",
            caller_address="So11111111111111111111111111111111111111113",
        )

    mock_complete.assert_called_once_with(
        execution_id=execution_id,
        agent_pda="So11111111111111111111111111111111111111112",
        agent_owner_address="So11111111111111111111111111111111111111112",
        ai_quality_score=85,
    )
    mock_refund.assert_not_called()
    assert result["complete_tx_hash"] == "fake_tx_hash"


@pytest.mark.asyncio
async def test_refund_execution_called_when_quality_low():
    """При score < threshold должен вызваться refund_execution_onchain."""
    from uuid import uuid4

    execution_id = str(uuid4())

    mock_evaluation = MagicMock()
    mock_evaluation.score = 40
    mock_evaluation.reasoning = "Poor"
    mock_evaluation.should_pay = False

    with patch("tasks.execute_task.get_coordinator") as mock_get_coord, \
         patch("tasks.execute_task.run_agent_in_sandbox") as mock_sandbox, \
         patch("tasks.execute_task.complete_execution_onchain") as mock_complete, \
         patch("tasks.execute_task.refund_execution_onchain") as mock_refund:

        mock_coordinator = AsyncMock()
        mock_get_coord.return_value = mock_coordinator
        mock_coordinator.evaluate_output = AsyncMock(return_value=mock_evaluation)
        mock_sandbox.return_value = {"error": "failed"}
        mock_complete.return_value = "fake_tx"
        mock_refund.return_value = "refund_tx"

        from tasks.execute_task import run_execution_with_evaluation

        result = await run_execution_with_evaluation(
            execution_id=execution_id,
            agent_slug="@user/test",
            agent_description="Test",
            input_data={"x": 1},
            agent_pda="So11111111111111111111111111111111111111112",
            agent_owner_address="So11111111111111111111111111111111111111112",
            caller_address="So11111111111111111111111111111111111111113",
        )

    mock_refund.assert_called_once_with(
        execution_id=execution_id,
        caller_address="So11111111111111111111111111111111111111113",
    )
    mock_complete.assert_not_called()
    assert result["complete_tx_hash"] == "refund_tx"
```

- [ ] **Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_execute_task.py -v 2>&1 | grep -E "(PASSED|FAILED)"
```

Expected: new tests FAIL — `run_execution_with_evaluation` doesn't accept on-chain params yet.

- [ ] **Step 3: Update run_execution_with_evaluation in execute_task.py**

Replace the `run_execution_with_evaluation` function added in Part 2:

```python
from services.onchain_billing import complete_execution_onchain, refund_execution_onchain


async def run_execution_with_evaluation(
    execution_id: str,
    agent_slug: str,
    agent_description: str,
    input_data: dict,
    agent_pda: str,
    agent_owner_address: str,
    caller_address: str,
) -> dict:
    """
    Запускает агента, оценивает результат, выполняет on-chain действие.

    Флоу:
    1. Запускаем агента в sandbox
    2. AI координатор оценивает качество (0-100)
    3. score >= threshold → complete_execution on-chain → SOL к автору
    4. score < threshold → refund_execution on-chain → SOL к вызывающему
    5. Возвращаем результат со всеми tx хешами
    """
    # 1. Запустить агента
    output = await run_agent_in_sandbox(
        agent_slug=agent_slug,
        input_data=input_data,
        execution_id=execution_id,
    )

    # 2. Оценить качество
    coordinator = get_coordinator()
    evaluation = await coordinator.evaluate_output(
        agent_slug=agent_slug,
        agent_description=agent_description,
        input_data=input_data,
        output_data=output,
    )

    # 3. On-chain действие на основе оценки
    complete_tx_hash = None
    if evaluation.should_pay:
        complete_tx_hash = await complete_execution_onchain(
            execution_id=execution_id,
            agent_pda=agent_pda,
            agent_owner_address=agent_owner_address,
            ai_quality_score=evaluation.score,
        )
    else:
        complete_tx_hash = await refund_execution_onchain(
            execution_id=execution_id,
            caller_address=caller_address,
        )

    return {
        "output": output,
        "ai_quality_score": evaluation.score,
        "ai_reasoning": evaluation.reasoning,
        "should_pay": evaluation.should_pay,
        "complete_tx_hash": complete_tx_hash,
    }
```

- [ ] **Step 4: Run all tests**

```bash
cd backend && python -m pytest tests/test_execute_task.py -v 2>&1 | grep -E "(PASSED|FAILED)"
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/execute_task.py
git commit -m "feat: wire on-chain complete/refund into execution pipeline"
```

---

## Task 5: Update POST /execute to save on-chain fields to DB

**Files:**
- Modify: `backend/routers/executions.py`

After the Celery task completes, update the Execution record with on-chain tx hashes and AI score.

- [ ] **Step 1: Find where execution status is updated in executions.py**

Open `backend/routers/executions.py`. Find the callback or polling logic that updates execution status after Celery task completes. It should look something like:

```python
execution.status = "done"
execution.output = result
```

- [ ] **Step 2: Add on-chain fields update**

In the same place where execution is updated after task completion, add:

```python
execution.ai_quality_score = result.get("ai_quality_score")
execution.ai_reasoning = result.get("ai_reasoning")
execution.complete_tx_hash = result.get("complete_tx_hash")
# on_chain_execution_id and on_chain_tx_hash are set when initiate_execution is called
```

- [ ] **Step 3: Update GET /executions/{id} response to include on-chain fields**

In the execution response schema (in `backend/schemas/execution.py`), add these fields to the response model:

```python
on_chain_execution_id: Optional[str] = None
on_chain_tx_hash: Optional[str] = None
complete_tx_hash: Optional[str] = None
ai_quality_score: Optional[int] = None
ai_reasoning: Optional[str] = None
```

Make sure `Optional` is imported: `from typing import Optional`

- [ ] **Step 4: Verify server starts**

```bash
cd backend && python -c "from main import app; print('OK')"
```

Expected: `OK` — no import errors.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/executions.py backend/schemas/execution.py
git commit -m "feat: expose on-chain tx hashes and AI score in execution API response"
```

---

## Task 6: register_agent on-chain when uploading

**Files:**
- Modify: `backend/routers/agents.py`
- Modify: `backend/models/agent.py`
- Modify: `backend/services/onchain_billing.py` — add register_agent_onchain()

- [ ] **Step 1: Add register_agent_onchain to onchain_billing.py**

Add to the end of `backend/services/onchain_billing.py`:

```python
async def register_agent_onchain(
    owner_address: str,
    slug: str,
    price_per_call_lamports: int,
) -> tuple[str, str]:
    """
    Вызывает register_agent в Anchor программе от имени platform (proxy).
    В production owner сам подписывает через frontend.
    Возвращает (agent_pda_address, tx_signature).
    """
    program_id = settings.anchor_program_id
    if not program_id:
        logger.warning("ANCHOR_PROGRAM_ID not set — skipping on-chain registration")
        return "", ""

    agent_pda, _ = get_agent_pda(owner_address, slug, program_id)
    platform_kp = _get_platform_keypair()

    # Данные: discriminator + slug (borsh string: 4 bytes len + bytes) + price (u64 le)
    slug_bytes = slug.encode()
    ix_data = (
        _discriminator("register_agent")
        + struct.pack("<I", len(slug_bytes))
        + slug_bytes
        + struct.pack("<Q", price_per_call_lamports)
    )

    accounts = [
        AccountMeta(pubkey=Pubkey.from_string(agent_pda), is_signer=False, is_writable=True),
        AccountMeta(pubkey=Pubkey.from_string(owner_address), is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
    ]

    instruction = Instruction(
        program_id=Pubkey.from_string(program_id),
        accounts=accounts,
        data=ix_data,
    )

    blockhash = await _get_recent_blockhash()
    tx = Transaction.new_signed_with_payer(
        instructions=[instruction],
        payer=platform_kp.pubkey(),
        signing_keypairs=[platform_kp],
        recent_blockhash=Hash.from_string(blockhash),
    )

    sig = await _send_transaction(tx)
    logger.info(f"register_agent tx: {sig}, pda={agent_pda}, slug={slug}")
    return agent_pda, sig
```

- [ ] **Step 2: Add on_chain fields to Agent model**

Open `backend/models/agent.py`. Add:

```python
on_chain_address = Column(String(88), nullable=True)   # AgentAccount PDA
register_tx_hash = Column(String(88), nullable=True)   # tx регистрации
```

- [ ] **Step 3: Create migration for agent on-chain fields**

```bash
cd .. && alembic revision -m "agent_onchain_fields"
```

Open the new migration file and replace upgrade/downgrade:

```python
def upgrade() -> None:
    op.add_column("agents", sa.Column("on_chain_address", sa.String(88), nullable=True))
    op.add_column("agents", sa.Column("register_tx_hash", sa.String(88), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "register_tx_hash")
    op.drop_column("agents", "on_chain_address")
```

Apply:
```bash
alembic upgrade head
```

- [ ] **Step 4: Call register_agent_onchain in agents.py upload endpoint**

Open `backend/routers/agents.py`. Find the POST endpoint that creates an agent (handles zip upload). After the agent is saved to DB, add:

```python
from services.onchain_billing import register_agent_onchain

# После сохранения агента в БД:
try:
    price_lamports = int(float(agent.price_per_call) * 1_000_000_000)
    agent_pda, register_tx = await register_agent_onchain(
        owner_address=current_user.wallet_address,
        slug=agent.slug,
        price_per_call_lamports=price_lamports,
    )
    if agent_pda:
        agent.on_chain_address = agent_pda
        agent.register_tx_hash = register_tx
        await db.commit()
        logger.info(f"Agent {agent.slug} registered on-chain: {agent_pda}")
except Exception as e:
    # On-chain registration failure не блокирует создание агента
    logger.error(f"On-chain registration failed for {agent.slug}: {e}")
```

- [ ] **Step 5: Verify server starts**

```bash
cd backend && python -c "from main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/services/onchain_billing.py backend/models/agent.py \
        alembic/versions/ backend/routers/agents.py
git commit -m "feat: register agent on-chain when uploading to marketplace"
```

---

## Verification Checklist

- [ ] All backend tests pass: `cd backend && python -m pytest tests/ -v`
- [ ] Alembic migrations applied: `alembic upgrade head` shows no pending
- [ ] Server starts: `cd backend && python -c "from main import app; print('OK')"`
- [ ] Agent upload triggers `register_agent_onchain` (check logs)
- [ ] Execution completes with `complete_tx_hash` in DB
- [ ] `git log --oneline` shows 6 commits from this plan
