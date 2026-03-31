"""Add on-chain fields to agents table

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("on_chain_address", sa.String(88), nullable=True))
    op.add_column("agents", sa.Column("register_tx_hash", sa.String(88), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "register_tx_hash")
    op.drop_column("agents", "on_chain_address")
