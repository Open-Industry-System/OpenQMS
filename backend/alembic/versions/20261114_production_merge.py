"""Merge current main and deployed production refresh-session histories.

Keep both existing revision identities so either deployed history can upgrade.
"""
revision = "20261114_production_merge"
down_revision = ("20261114_r4b_main_merge", "20260913_user_refresh_sessions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
