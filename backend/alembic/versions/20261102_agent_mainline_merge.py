"""Merge the published single-report and runtime Agent migration branches."""

revision = "20261102_agent_mainline_merge"
down_revision = ("20260929_agent_read_task", "20261009_agent_task_attachments")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
