"""Add GitHub OAuth columns to users

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("github_username", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))
    op.create_unique_constraint("uq_users_github_id", "users", ["github_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_github_id", "users")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "github_username")
    op.drop_column("users", "github_id")
