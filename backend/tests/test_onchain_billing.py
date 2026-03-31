"""Тесты onchain_billing — PDA вычисления и вспомогательные функции."""

import pytest
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
