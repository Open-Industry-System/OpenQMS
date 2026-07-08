"""Add capa_ppt_export + agent_review_skill tables (US-E2E-01.10)

Revision ID: 20260708_capa_ppt_review_sk
Revises: 20260708_d7_node_action_status
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260708_capa_ppt_review_sk"
# ↓↓↓ 必须替换为 Step 0 `alembic heads` 记录的真实 head（如 "20260708_d7_node_action_status"）。
# ↓↓↓ 保留尖括号占位符 <...> = 无效迁移，alembic upgrade 会报 Can't locate revision。
down_revision = "20260708_d7_node_action_status"
branch_labels = None
depends_on = None


DEFAULT_REVIEW_SKILL_CONTENT = """## 8D 报告 PPT 审查标准

审查 PPT 内容是否符合 8D 报告要求：
1. 封面齐全（8D 单号、标题、严重度、产品线、发起人、状态、日期）
2. D1-D8 各页非空，内容来自落库数据
3. D4 根因分析含验证记录（method/result/is_verified + 证据附件引用）
4. D7 预防复发含 node-action 处置记录
5. 联动附录含关联 FMEA 节点详情 + SCAR/供应商风险预警单号与状态
6. 生成信息页含版本与审查状态
返回 JSON: {passed: bool, issues: [str], suggestions: [str]}
"""


def upgrade() -> None:
    op.create_table(
        "capa_ppt_export",
        sa.Column("export_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_schema", sa.String(63)),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("file_url", sa.String(500)),
        sa.Column("review_status", sa.String(20), server_default="skipped", nullable=False),
        sa.Column("review_rounds", sa.Integer, server_default="0", nullable=False),
        sa.Column("review_report", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_capa_ppt_export_capa_id", "capa_ppt_export", ["capa_id"])

    op.create_table(
        "agent_review_skill",
        sa.Column("skill_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_schema", sa.String(63)),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # COALESCE 唯一索引：防多个 tenant_schema=NULL 同名 skill（PG NULL != NULL）
    op.create_index(
        "uq_review_skill_tenant_name",
        "agent_review_skill",
        [sa.text("COALESCE(tenant_schema, '')"), "name"],
        unique=True,
    )
    # seed 默认 skill（tenant_schema='public' 全局默认，供租户回退）
    op.execute(
        sa.text("""
            INSERT INTO agent_review_skill (skill_id, tenant_schema, name, content, version, is_active)
            VALUES (gen_random_uuid(), 'public', 'capa_ppt_review', :content, 1, true)
            ON CONFLICT DO NOTHING
        """).bindparams(sa.bindparam("content", DEFAULT_REVIEW_SKILL_CONTENT))
    )


def downgrade() -> None:
    op.drop_index("uq_review_skill_tenant_name", table_name="agent_review_skill")
    op.drop_index("ix_capa_ppt_export_capa_id", table_name="capa_ppt_export")
    op.drop_table("agent_review_skill")
    op.drop_table("capa_ppt_export")
