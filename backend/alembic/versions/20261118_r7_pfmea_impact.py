"""Store R7 impact bindings and append-only evidence in the local business schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261118_r7_pfmea_impact"
down_revision = "20261118_r6_security_merge"
branch_labels = None
depends_on = None


def _schema():
    connection = op.get_bind()
    schema = connection.scalar(sa.text("SELECT current_schema()"))
    return connection.dialect.identifier_preparer.quote_schema(schema)


def upgrade():
    op.create_table(
        "agent_pfmea_impact_bindings",
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), primary_key=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("binding", JSONB, nullable=False),
        sa.Column("binding_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("actor_id", "request_key", name="uq_r7_impact_actor_request"),
        sa.CheckConstraint("length(btrim(request_key)) > 0", name="ck_r7_impact_request_key"),
        sa.CheckConstraint("binding_digest ~ '^[0-9a-f]{64}$'", name="ck_r7_impact_binding_digest"),
        sa.CheckConstraint(
            "jsonb_typeof(binding) = 'object' AND octet_length(binding::text) <= 524288",
            name="ck_r7_impact_binding_shape",
        ),
    )
    op.create_table(
        "agent_pfmea_impact_receipts",
        sa.Column("receipt_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("agent_pfmea_impact_bindings.task_id"), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False),
        sa.Column("lease_epoch", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("scope_digest", sa.String(64), nullable=False),
        sa.Column("page_key", sa.String(64)),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("lease_epoch >= 0", name="ck_r7_impact_receipt_epoch"),
        sa.CheckConstraint(
            "kind IN ('release', 'page_confirmation', 'coverage')",
            name="ck_r7_impact_receipt_kind",
        ),
        sa.CheckConstraint("scope_digest ~ '^[0-9a-f]{64}$'", name="ck_r7_impact_scope_digest"),
        sa.CheckConstraint(
            "(page_key IS NULL OR page_key ~ '^[0-9a-f]{64}$') "
            "AND (kind <> 'page_confirmation' OR page_key IS NOT NULL) "
            "AND (kind <> 'coverage' OR page_key IS NULL)",
            name="ck_r7_impact_receipt_page",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 524288",
            name="ck_r7_impact_receipt_shape",
        ),
    )
    op.create_index("ix_r7_impact_run_receipts", "agent_pfmea_impact_receipts", ["run_id", "lease_epoch", "kind"])
    op.create_index(
        "uq_r7_impact_page_confirmation", "agent_pfmea_impact_receipts",
        ["run_id", "lease_epoch", "scope_digest", "page_key"], unique=True,
        postgresql_where=sa.text("kind = 'page_confirmation'"),
    )
    op.create_table(
        "agent_pfmea_impact_result_receipts",
        sa.Column("result_id", UUID(as_uuid=True), sa.ForeignKey("agent_results.result_id"), primary_key=True),
        sa.Column(
            "receipt_id", UUID(as_uuid=True), sa.ForeignKey("agent_pfmea_impact_receipts.receipt_id"),
            primary_key=True,
        ),
    )

    schema = _schema()
    op.execute(f"""
CREATE FUNCTION {schema}.r7_impact_ledger_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'R7 evidence is immutable' USING ERRCODE='23514';
    END IF;
    CASE TG_TABLE_NAME
        WHEN 'agent_pfmea_impact_bindings' THEN
            IF NOT EXISTS (SELECT 1 FROM {schema}.agent_tasks
                            WHERE task_id=NEW.task_id AND initiator_id=NEW.actor_id) THEN
                RAISE EXCEPTION 'R7 binding actor does not match task' USING ERRCODE='23514';
            END IF;
        WHEN 'agent_pfmea_impact_receipts' THEN
            IF NOT EXISTS (SELECT 1 FROM {schema}.agent_runs
                            WHERE run_id=NEW.run_id AND task_id=NEW.task_id) THEN
                RAISE EXCEPTION 'R7 receipt run does not match task' USING ERRCODE='23514';
            END IF;
        WHEN 'agent_pfmea_impact_result_receipts' THEN
            IF NOT EXISTS (
                SELECT 1 FROM {schema}.agent_results AS result
                JOIN {schema}.agent_pfmea_impact_receipts AS receipt
                  ON receipt.task_id=result.task_id AND receipt.run_id=result.run_id
                WHERE result.result_id=NEW.result_id AND receipt.receipt_id=NEW.receipt_id
            ) THEN
                RAISE EXCEPTION 'R7 receipt does not match result run' USING ERRCODE='23514';
            END IF;
    END CASE;
    RETURN NEW;
END $$
""")
    for table in (
        "agent_pfmea_impact_bindings",
        "agent_pfmea_impact_receipts",
        "agent_pfmea_impact_result_receipts",
    ):
        op.execute(f"""
CREATE TRIGGER r7_impact_ledger_guard BEFORE INSERT OR UPDATE OR DELETE ON {schema}.{table}
FOR EACH ROW EXECUTE FUNCTION {schema}.r7_impact_ledger_guard()
""")

    op.execute(f"""
CREATE FUNCTION {schema}.r7_impact_result_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    expected_digest text;
BEGIN
    IF TG_OP <> 'INSERT' AND EXISTS (
        SELECT 1 FROM {schema}.agent_pfmea_impact_bindings WHERE task_id=OLD.task_id
    ) THEN
        RAISE EXCEPTION 'R7 result is immutable' USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    SELECT binding_digest INTO expected_digest
      FROM {schema}.agent_pfmea_impact_bindings WHERE task_id=NEW.task_id;
    IF expected_digest IS NULL THEN
        IF NEW.payload->>'contract' = 'pfmea_impact_result.v1' THEN
            RAISE EXCEPTION 'R7 result requires a bound task' USING ERRCODE='23514';
        END IF;
    ELSIF TG_OP <> 'INSERT'
          OR NEW.payload->>'contract' IS DISTINCT FROM 'pfmea_impact_result.v1'
          OR NEW.payload->>'binding_digest' IS DISTINCT FROM expected_digest
          OR NOT EXISTS (SELECT 1 FROM {schema}.agent_runs
                         WHERE run_id=NEW.run_id AND task_id=NEW.task_id) THEN
        RAISE EXCEPTION 'R7 result does not match its binding' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$
""")
    op.execute(f"""
CREATE TRIGGER r7_impact_result_guard BEFORE INSERT OR UPDATE OR DELETE ON {schema}.agent_results
FOR EACH ROW EXECUTE FUNCTION {schema}.r7_impact_result_guard()
""")

    op.add_column("fmea_documents", sa.Column(
        "r7_scope_generation", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()"),
    ))
    # There is deliberately no backfill on the version table. A prior approval
    # cannot acquire a publication-time scope by observing today's document.
    op.add_column("fmea_versions", sa.Column("r7_approved_scope_generation", UUID(as_uuid=True), nullable=True))
    op.execute(f"""
CREATE FUNCTION {schema}.r7_impact_target_generation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.r7_scope_generation := gen_random_uuid();
    ELSIF NEW.r7_scope_generation IS DISTINCT FROM OLD.r7_scope_generation THEN
        RAISE EXCEPTION 'R7 target generation is managed by the database' USING ERRCODE='23514';
    ELSIF (NEW.fmea_id, NEW.factory_id, NEW.product_line_code, NEW.fmea_type)
          IS DISTINCT FROM (OLD.fmea_id, OLD.factory_id, OLD.product_line_code, OLD.fmea_type) THEN
        NEW.r7_scope_generation := gen_random_uuid();
    END IF;
    RETURN NEW;
END $$
""")
    op.execute(f"""
CREATE TRIGGER r7_impact_target_generation BEFORE INSERT OR UPDATE ON {schema}.fmea_documents
FOR EACH ROW EXECUTE FUNCTION {schema}.r7_impact_target_generation()
""")
    op.execute(f"""
CREATE FUNCTION {schema}.r7_impact_approval_generation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.r7_approved_scope_generation IS DISTINCT FROM OLD.r7_approved_scope_generation
           OR (OLD.r7_approved_scope_generation IS NOT NULL
               AND (NEW.version_id, NEW.fmea_id, NEW.factory_id, NEW.major_no, NEW.minor_no,
                    NEW.change_type, NEW.snapshot, NEW.sha256_hash)
                   IS DISTINCT FROM (OLD.version_id, OLD.fmea_id, OLD.factory_id, OLD.major_no, OLD.minor_no,
                    OLD.change_type, OLD.snapshot, OLD.sha256_hash)) THEN
            RAISE EXCEPTION 'R7 approval scope is immutable' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    NEW.r7_approved_scope_generation := NULL;
    IF NEW.change_type = 'approve' AND NEW.major_no > 0 AND NEW.minor_no = 0 THEN
        SELECT r7_scope_generation INTO NEW.r7_approved_scope_generation
          FROM {schema}.fmea_documents
         WHERE fmea_id=NEW.fmea_id AND factory_id=NEW.factory_id AND fmea_type='PFMEA'
           FOR SHARE;
    END IF;
    RETURN NEW;
END $$
""")
    op.execute(f"""
CREATE TRIGGER r7_impact_approval_generation BEFORE INSERT OR UPDATE ON {schema}.fmea_versions
FOR EACH ROW EXECUTE FUNCTION {schema}.r7_impact_approval_generation()
""")


def downgrade():
    schema = _schema()
    bind = op.get_bind()
    tables = (
        "agent_pfmea_impact_result_receipts", "agent_pfmea_impact_receipts", "agent_pfmea_impact_bindings",
    )
    # Serialise the check and DROP operations against new durable evidence.
    bind.execute(sa.text(
        "LOCK TABLE " + ", ".join(f"{schema}.{name}" for name in reversed(tables)) + " IN ACCESS EXCLUSIVE MODE"
    ))
    if bind.scalar(sa.text("SELECT " + " OR ".join(
        f"EXISTS (SELECT 1 FROM {schema}.{name})" for name in tables
    ))):
        raise RuntimeError("R7 evidence exists; downgrade refused")
    op.execute(f"DROP TRIGGER r7_impact_result_guard ON {schema}.agent_results")
    op.execute(f"DROP FUNCTION {schema}.r7_impact_result_guard()")
    op.execute(f"DROP TRIGGER r7_impact_approval_generation ON {schema}.fmea_versions")
    op.execute(f"DROP FUNCTION {schema}.r7_impact_approval_generation()")
    op.drop_column("fmea_versions", "r7_approved_scope_generation")
    op.execute(f"DROP TRIGGER r7_impact_target_generation ON {schema}.fmea_documents")
    op.execute(f"DROP FUNCTION {schema}.r7_impact_target_generation()")
    op.drop_column("fmea_documents", "r7_scope_generation")
    for table in tables:
        op.drop_table(table)
    op.execute(f"DROP FUNCTION {schema}.r7_impact_ledger_guard()")
