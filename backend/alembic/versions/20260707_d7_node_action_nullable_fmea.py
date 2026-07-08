"""D7 node action: allow rule-engine fallback rows (no linked FMEA).

Revision ID: 20260707_d7_null_fmea
Revises: 20260706_lessons
Create Date: 2026-07-07

背景：US-E2E-01 验收发现 D7 预防节点动作在无 FMEA 命中时不出现。补规则引擎兜底推荐后，
这些兜底推荐没有关联 FMEA（fmea_id 为空），需要 capa_d7_node_action.fmea_id 可空以记录
confirm/skip 动作。failure_mode_node_id 保持非空，兜底推荐用合成 key（rule:<hash>）。
唯一索引改为 COALESCE(fmea_id, 零 UUID) 以便兜底行也能去重。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20260707_d7_null_fmea"
down_revision: str | None = "20260706_lessons"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE capa_d7_node_action ALTER COLUMN fmea_id DROP NOT NULL")
    # 重建唯一索引：fmea_id 为空时按零 UUID 归口，兜底行也能去重
    op.execute("DROP INDEX IF EXISTS ix_capa_d7_node_unique")
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_d7_node_unique ON capa_d7_node_action "
        "(capa_id, COALESCE(fmea_id, '00000000-0000-0000-0000-000000000000'::uuid), "
        "failure_mode_node_id, COALESCE(failure_cause_node_id, ''))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_capa_d7_node_unique")
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_d7_node_unique ON capa_d7_node_action "
        "(capa_id, fmea_id, failure_mode_node_id, COALESCE(failure_cause_node_id, ''))"
    )
    # 回滚为 NOT NULL 前需清掉空 fmea_id 行（兜底动作），否则 ALTER 失败
    op.execute("DELETE FROM capa_d7_node_action WHERE fmea_id IS NULL")
    op.execute("ALTER TABLE capa_d7_node_action ALTER COLUMN fmea_id SET NOT NULL")