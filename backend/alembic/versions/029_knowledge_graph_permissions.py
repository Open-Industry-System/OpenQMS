"""add knowledge_graph permissions

Revision ID: 029
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = '029_knowledge_graph_permissions'
down_revision: Union[str, None] = '20260602_collab_sessions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO role_permissions (role_id, module, permission_level) "
        "SELECT id, 'knowledge_graph', 1 FROM role_definitions WHERE role_key = 'admin'"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, module, permission_level) "
        "SELECT id, 'knowledge_graph', 1 FROM role_definitions WHERE role_key = 'manager'"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE module = 'knowledge_graph'"
    )
