"""Add cp validation tables.

Revision ID: 20260610_add_cp_validation
Revises: 032_lessons_learned_cache
Create Date: 2026-06-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260610_add_cp_validation"
down_revision: Union[str, None] = "032_lessons_learned_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guard: t001_tenant_squash may have already created these tables via
    # metadata.create_all(CHECKFIRST).  Use raw SQL with IF NOT EXISTS to
    # avoid DuplicateTableError when running after t001.
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS cp_validation_runs (
            run_id UUID DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
            cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
            trigger VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed')),
            rule_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            info_count INTEGER DEFAULT 0,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            completed_at TIMESTAMP WITH TIME ZONE,
            failed_rules JSONB DEFAULT '[]'::jsonb,
            created_by UUID REFERENCES users(user_id) ON DELETE SET NULL
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cpvrn_cp_id ON cp_validation_runs (cp_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cpvrn_status ON cp_validation_runs (status)"
    ))
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cpvrn_running "
        "ON cp_validation_runs (cp_id) WHERE status = 'running'"
    ))

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS cp_validation_findings (
            finding_id UUID DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
            cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
            finding_hash VARCHAR(64) NOT NULL,
            rule_id VARCHAR(20) NOT NULL,
            severity VARCHAR(10) NOT NULL
                CHECK (severity IN ('error', 'warning', 'info')),
            category VARCHAR(20) NOT NULL
                CHECK (category IN ('coverage', 'consistency', 'completeness', 'risk', 'optimization')),
            status VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'accepted', 'rejected', 'resolved')),
            resolved_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
            resolved_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cvf_cp_id ON cp_validation_findings (cp_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cvf_status ON cp_validation_findings (status)"
    ))
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cvf_hash "
        "ON cp_validation_findings (cp_id, finding_hash)"
    ))

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS cp_validation_occurrences (
            occurrence_id UUID DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
            run_id UUID NOT NULL REFERENCES cp_validation_runs(run_id) ON DELETE CASCADE,
            finding_id UUID NOT NULL REFERENCES cp_validation_findings(finding_id) ON DELETE CASCADE,
            cp_id UUID NOT NULL REFERENCES control_plans(cp_id) ON DELETE CASCADE,
            validation_type VARCHAR(20) NOT NULL
                CHECK (validation_type IN ('rule', 'llm', 'recommendation')),
            title VARCHAR(200) NOT NULL,
            description TEXT,
            affected_items JSONB DEFAULT '[]'::jsonb,
            fmea_node_ids JSONB DEFAULT '[]'::jsonb,
            suggestion TEXT,
            suggestion_data JSONB,
            present BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cvo_run_id ON cp_validation_occurrences (run_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cvo_finding_id ON cp_validation_occurrences (finding_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_cvo_cp_id ON cp_validation_occurrences (cp_id)"
    ))
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cvo_run_finding "
        "ON cp_validation_occurrences (run_id, finding_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvo_run_finding"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvo_cp_id"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvo_finding_id"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvo_run_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS cp_validation_occurrences"))

    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvf_hash"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvf_status"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cvf_cp_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS cp_validation_findings"))

    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cpvrn_running"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cpvrn_status"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_cpvrn_cp_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS cp_validation_runs"))
