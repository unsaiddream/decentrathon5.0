"""agent_secrets table

Revision ID: 002
Revises: 001
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_secrets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.String(2000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'agent_id', 'key', name='uq_secret_user_agent_key'),
    )
    op.create_index('ix_agent_secrets_user_agent', 'agent_secrets', ['user_id', 'agent_id'])


def downgrade() -> None:
    op.drop_index('ix_agent_secrets_user_agent', table_name='agent_secrets')
    op.drop_table('agent_secrets')
