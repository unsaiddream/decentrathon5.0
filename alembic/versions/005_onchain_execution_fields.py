"""Add on-chain fields to executions table

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


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
