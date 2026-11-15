"""Join published R5 and current-main histories without replaying either branch."""

revision = "20261115_r5_main_merge"
down_revision = ("20261114_r5_models", "20261114_production_merge")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
