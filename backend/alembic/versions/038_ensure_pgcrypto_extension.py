"""ensure pgcrypto extension exists for digest() function

Migration 020 uses digest() in a trigger but doesn't ensure the pgcrypto
extension is installed. This migration creates the extension if it
doesn't already exist (idempotent: CREATE EXTENSION IF NOT EXISTS).

Revision ID: 038
Revises: 037_lock_version_not_null
"""
from alembic import op


revision = '038'
down_revision = '037_lock_version_not_null'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')


def downgrade() -> None:
    # Don't remove pgcrypto on downgrade — other migrations may depend on it
    pass