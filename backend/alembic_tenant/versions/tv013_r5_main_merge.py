"""Join published R5 and refresh-session tenant histories."""

revision = "tv013_r5_main_merge"
down_revision = ("tv012_r5_models", "tv010_refresh_sessions")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
