"""Join the existing read-task and runtime foundations without rewriting either.

Revision ID: 20261103_merge_agent_foundations
Revises: 20260929_agent_read_task, 20261009_agent_task_attachments
"""

revision = "20261103_merge_agent_foundations"
down_revision = ("20260929_agent_read_task", "20261009_agent_task_attachments")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
