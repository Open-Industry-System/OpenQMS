"""add capa verification adoption tables

Revision ID: 20260703_capa_verif
Revises: c0b6287b3d61
Create Date: 2026-07-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260703_capa_verif"
down_revision: Union[str, None] = "c0b6287b3d61"   # ← 替换为 Step 1 记下的 head revision
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capa_root_cause_verification",
        sa.Column("verification_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("root_cause_text", sa.Text, nullable=False),
        sa.Column("method", sa.Text),
        sa.Column("result", sa.Text),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("evidence_attachments", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_ref", postgresql.JSONB),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_rcv_capa_id", "capa_root_cause_verification", ["capa_id"])
    op.create_index("ix_capa_rcv_factory", "capa_root_cause_verification", ["factory_id"])

    op.create_table(
        "capa_ai_adoption",
        sa.Column("adoption_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("d_step", sa.String(8), nullable=False),
        sa.Column("adopted_text", sa.Text, nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("stage_index", sa.Integer),
        sa.Column("item_ref", postgresql.JSONB),
        sa.Column("adopted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_adopt_capa_step", "capa_ai_adoption", ["capa_id", "d_step"])
    op.create_index("ix_capa_adopt_factory", "capa_ai_adoption", ["factory_id"])
    # 幂等去重：同 (capa, d_step, source, item_ref, adopted_text) 重复采纳 → 命中 unique 兜底，服务层 catch 后返回既有 adoption
    # 用 md5(...) 哈希表达式而非原始 TEXT，避免长 LLM 文本 / 大 item_ref 超过 Postgres btree 索引项最大字节数导致 insert 失败
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_ai_adoption_dedupe ON capa_ai_adoption "
        "(capa_id, d_step, source, md5(COALESCE(item_ref::text, '')), md5(adopted_text))"
    )

    op.create_table(
        "capa_d7_node_action",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("fmea_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False),
        sa.Column("failure_mode_node_id", sa.String(128), nullable=False),
        sa.Column("failure_cause_node_id", sa.String(128)),
        sa.Column("match_source", sa.String(40), nullable=False),
        sa.Column("prevention_control_node_id", sa.String(128)),
        sa.Column("prevention_control_name_before", sa.Text),
        sa.Column("prevention_control_name_after", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("acted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_d7_capa", "capa_d7_node_action", ["capa_id"])
    op.create_index("ix_capa_d7_factory", "capa_d7_node_action", ["factory_id"])
    # 表达式唯一索引（COALESCE 收口 nullable failure_cause_node_id，见 R3-Finding 4）
    op.execute(
        "CREATE UNIQUE INDEX ix_capa_d7_node_unique ON capa_d7_node_action "
        "(capa_id, fmea_id, failure_mode_node_id, COALESCE(failure_cause_node_id, ''))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_capa_d7_node_unique")
    op.drop_index("ix_capa_d7_factory", table_name="capa_d7_node_action")
    op.drop_index("ix_capa_d7_capa", table_name="capa_d7_node_action")
    op.drop_table("capa_d7_node_action")
    op.execute("DROP INDEX IF EXISTS ix_capa_ai_adoption_dedupe")
    op.drop_index("ix_capa_adopt_factory", table_name="capa_ai_adoption")
    op.drop_index("ix_capa_adopt_capa_step", table_name="capa_ai_adoption")
    op.drop_table("capa_ai_adoption")
    op.drop_index("ix_capa_rcv_factory", table_name="capa_root_cause_verification")
    op.drop_index("ix_capa_rcv_capa_id", table_name="capa_root_cause_verification")
    op.drop_table("capa_root_cause_verification")
