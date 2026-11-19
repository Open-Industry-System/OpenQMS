"""Version IQC facts independently of investigation links."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "tv026_r7_iqc_facts"
down_revision = "tv025_r7_pfmea_impact"
branch_labels = None
depends_on = None

# Explicitly exclude mutable links to third-party investigations and timestamps.
FACT_FIELDS = (
    "inspection_id inspection_no supplier_id part_no part_name lot_no lot_qty "
    "sample_qty aql_level inspection_level sampling_standard inspection_result "
    "defect_qty defect_description inspection_date inspected_by inspection_mode "
    "material_id template_id code_letter accept_number reject_number status "
    "re_inspection parent_inspection_id product_line_code factory_id judged_by "
    "judged_at has_safety_defect"
).split()


def _schema():
    connection = op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(
        connection.scalar(sa.text("SELECT current_schema()"))
    )


def upgrade():
    schema = _schema()
    op.add_column("iqc_inspections", sa.Column(
        "identity_generation", sa.Uuid(), nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    ))
    op.add_column("iqc_inspections", sa.Column(
        "inspection_revision", sa.BigInteger(), nullable=False, server_default=sa.text("1"),
    ))
    op.create_unique_constraint(
        "uq_iqc_inspection_factory", "iqc_inspections", ["inspection_id", "factory_id"],
    )
    op.add_column("agent_tasks", sa.Column(
        "task_type", sa.String(40), nullable=False, server_default="capa",
    ))
    op.add_column("agent_tasks", sa.Column("target_iqc_inspection_id", sa.Uuid(), nullable=True))
    op.alter_column("agent_tasks", "target_capa_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key("fk_agent_task_iqc_factory", "agent_tasks", "iqc_inspections",
                          ["target_iqc_inspection_id", "factory_id"], ["inspection_id", "factory_id"])
    op.create_check_constraint(
        "ck_agent_task_typed_anchor", "agent_tasks",
        "(task_type = 'capa' AND target_capa_id IS NOT NULL AND target_iqc_inspection_id IS NULL)"
        " OR (task_type = 'iqc_investigation_advice.v1' AND target_capa_id IS NULL"
        " AND target_iqc_inspection_id IS NOT NULL)",
    )
    op.create_table(
        "agent_iqc_investigation_bindings",
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_tasks.task_id"), primary_key=True),
        sa.Column("binding", JSONB, nullable=False),
        sa.Column("binding_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("binding_digest ~ '^[0-9a-f]{64}$'", name="ck_iqc_binding_digest"),
        sa.CheckConstraint(
            "jsonb_typeof(binding) = 'object' AND octet_length(binding::text) <= 16384",
            name="ck_iqc_binding_shape",
        ),
    )
    op.create_table(
        "agent_iqc_investigation_receipts",
        sa.Column("receipt_id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("agent_iqc_investigation_bindings.task_id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("agent_runs.run_id"), nullable=False),
        sa.Column("lease_epoch", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("lease_epoch >= 0", name="ck_iqc_receipt_epoch"),
        sa.CheckConstraint("kind IN ('source', 'model_attempt')", name="ck_iqc_receipt_kind"),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 524288",
            name="ck_iqc_receipt_shape",
        ),
    )
    op.create_index("ix_iqc_investigation_run_receipts", "agent_iqc_investigation_receipts", ["run_id", "lease_epoch"])
    op.execute(f"""
CREATE FUNCTION {schema}.iqc_investigation_ledger_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'IQC investigation snapshots are immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'agent_iqc_investigation_bindings' THEN
        IF NOT EXISTS (
            SELECT 1 FROM {schema}.agent_tasks WHERE task_id = NEW.task_id
              AND task_type = 'iqc_investigation_advice.v1'
              AND target_iqc_inspection_id::text = NEW.binding->>'inspection_id'
              AND factory_id::text = NEW.binding->>'factory_id'
        ) THEN
            RAISE EXCEPTION 'IQC investigation binding target mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF NOT EXISTS (
        SELECT 1 FROM {schema}.agent_runs WHERE run_id = NEW.run_id
          AND task_id = NEW.task_id AND lease_epoch = NEW.lease_epoch AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'IQC investigation receipt run mismatch' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$
""")
    for table in ("agent_iqc_investigation_bindings", "agent_iqc_investigation_receipts"):
        op.execute(f"""
CREATE TRIGGER iqc_investigation_ledger_guard BEFORE INSERT OR UPDATE OR DELETE ON {schema}.{table}
FOR EACH ROW EXECUTE FUNCTION {schema}.iqc_investigation_ledger_guard()
""")
    op.execute(f"""
CREATE FUNCTION {schema}.iqc_investigation_result_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    selected_task uuid := CASE WHEN TG_OP = 'DELETE' THEN OLD.task_id ELSE NEW.task_id END;
    expected_digest text;
BEGIN
    SELECT binding_digest INTO expected_digest
      FROM {schema}.agent_iqc_investigation_bindings WHERE task_id = selected_task;
    IF TG_OP <> 'INSERT' AND EXISTS (
        SELECT 1 FROM {schema}.agent_iqc_investigation_bindings WHERE task_id = OLD.task_id
    ) THEN
        RAISE EXCEPTION 'IQC investigation result is immutable' USING ERRCODE = '23514';
    END IF;
    IF expected_digest IS NULL THEN
        IF TG_OP <> 'DELETE' AND NEW.payload->>'contract' = 'iqc_investigation_result.v1' THEN
            RAISE EXCEPTION 'IQC investigation result requires a bound task' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_OP <> 'INSERT'
          OR NEW.payload->>'contract' IS DISTINCT FROM 'iqc_investigation_result.v1'
          OR NEW.payload->>'binding_digest' IS DISTINCT FROM expected_digest
          OR NOT EXISTS (
              SELECT 1 FROM {schema}.agent_runs WHERE run_id = NEW.run_id AND task_id = selected_task
          ) THEN
        RAISE EXCEPTION 'IQC investigation result binding mismatch' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$
""")
    op.execute(f"""
CREATE TRIGGER iqc_investigation_result_guard BEFORE INSERT OR UPDATE OR DELETE ON {schema}.agent_results
FOR EACH ROW EXECUTE FUNCTION {schema}.iqc_investigation_result_guard()
""")
    op.execute(f"""
CREATE FUNCTION {schema}.iqc_association_write_fence() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    -- Ordinary writers can run concurrently. Only final IQC publication excludes them.
    PERFORM pg_advisory_xact_lock_shared(hashtextextended('openqms.iqc-associations.v1:' || TG_TABLE_SCHEMA, 0));
    RETURN NULL;
END $$
""")
    for table, events in (
        ("iqc_inspections", "INSERT OR DELETE OR UPDATE OF parent_inspection_id, linked_scar_id, linked_capa_id"),
        ("supplier_scars", "INSERT OR DELETE OR UPDATE OF scar_id, factory_id, product_line_code, "
         "source_type, source_id, capa_ref_id, description, status, scar_no, created_at"),
        ("capa_eightd", "INSERT OR DELETE OR UPDATE OF report_id, factory_id, product_line_code, "
         "scar_ref_id, title, status, document_no, created_at"),
    ):
        op.execute(f"""
CREATE TRIGGER iqc_association_write_fence BEFORE {events} ON {schema}.{table}
FOR EACH STATEMENT EXECUTE FUNCTION {schema}.iqc_association_write_fence()
""")
    old, new = (", ".join(f"{prefix}.{field}" for field in FACT_FIELDS) for prefix in ("OLD", "NEW"))
    op.execute(f"""
CREATE FUNCTION {schema}.iqc_fact_revision_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.identity_generation := gen_random_uuid();
        NEW.inspection_revision := 1;
    ELSIF NEW.identity_generation IS DISTINCT FROM OLD.identity_generation THEN
        RAISE EXCEPTION 'IQC identity is database-managed' USING ERRCODE = '23514';
    ELSIF ROW({old}) IS DISTINCT FROM ROW({new}) THEN
        NEW.inspection_revision := OLD.inspection_revision + 1;
    ELSIF NEW.inspection_revision IS DISTINCT FROM OLD.inspection_revision
          AND (pg_trigger_depth() < 2 OR NEW.inspection_revision <> OLD.inspection_revision + 1) THEN
        RAISE EXCEPTION 'IQC revision is database-managed' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute(f"""
CREATE TRIGGER iqc_fact_revision_guard
BEFORE INSERT OR UPDATE ON {schema}.iqc_inspections
FOR EACH ROW EXECUTE FUNCTION {schema}.iqc_fact_revision_guard();

""")
    op.execute(f"""
CREATE FUNCTION {schema}.iqc_revise_from_detail() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE
    old_id uuid;
    new_id uuid;
    anchor uuid;
BEGIN
    IF TG_OP = 'UPDATE' AND OLD IS NOT DISTINCT FROM NEW THEN
        RETURN NULL;
    END IF;
    IF TG_TABLE_NAME = 'iqc_inspection_items' THEN
        IF TG_OP <> 'INSERT' THEN old_id := OLD.inspection_id; END IF;
        IF TG_OP <> 'DELETE' THEN new_id := NEW.inspection_id; END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN
            EXECUTE format('SELECT inspection_id FROM %I.iqc_inspection_items WHERE item_id = $1',
                           TG_TABLE_SCHEMA) INTO old_id USING OLD.item_id;
        END IF;
        IF TG_OP <> 'DELETE' THEN
            EXECUTE format('SELECT inspection_id FROM %I.iqc_inspection_items WHERE item_id = $1',
                           TG_TABLE_SCHEMA) INTO new_id USING NEW.item_id;
        END IF;
    END IF;
    FOR anchor IN SELECT DISTINCT value
                  FROM unnest(ARRAY[old_id, new_id]) AS source(value)
                  WHERE value IS NOT NULL ORDER BY value
    LOOP
        EXECUTE format('UPDATE %I.iqc_inspections SET inspection_revision = inspection_revision + 1'
                       ' WHERE inspection_id = $1', TG_TABLE_SCHEMA) USING anchor;
    END LOOP;
    RETURN NULL;
END $$;
""")
    op.execute(f"""
CREATE TRIGGER iqc_item_fact_revision AFTER INSERT OR UPDATE OR DELETE ON {schema}.iqc_inspection_items
FOR EACH ROW EXECUTE FUNCTION {schema}.iqc_revise_from_detail();
""")
    op.execute(f"""
CREATE TRIGGER iqc_measurement_fact_revision AFTER INSERT OR UPDATE OR DELETE ON {schema}.iqc_item_measurements
FOR EACH ROW EXECUTE FUNCTION {schema}.iqc_revise_from_detail();
""")


def downgrade():
    schema = _schema()
    bind = op.get_bind()
    bind.execute(sa.text(f"LOCK TABLE {schema}.agent_tasks IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {schema}.agent_tasks WHERE task_type <> 'capa')")):
        raise RuntimeError("IQC tasks exist; downgrade refused")
    for table in ("iqc_inspections", "supplier_scars", "capa_eightd"):
        op.execute(f"DROP TRIGGER iqc_association_write_fence ON {schema}.{table}")
    op.execute(f"DROP FUNCTION {schema}.iqc_association_write_fence()")
    op.execute(f"DROP TRIGGER iqc_investigation_result_guard ON {schema}.agent_results")
    op.execute(f"DROP FUNCTION {schema}.iqc_investigation_result_guard()")
    op.drop_table("agent_iqc_investigation_receipts")
    op.drop_table("agent_iqc_investigation_bindings")
    op.execute(f"DROP FUNCTION {schema}.iqc_investigation_ledger_guard()")
    op.drop_constraint("ck_agent_task_typed_anchor", "agent_tasks", type_="check")
    op.drop_constraint("fk_agent_task_iqc_factory", "agent_tasks", type_="foreignkey")
    op.alter_column("agent_tasks", "target_capa_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("agent_tasks", "target_iqc_inspection_id")
    op.drop_column("agent_tasks", "task_type")
    op.execute(f"DROP TRIGGER iqc_measurement_fact_revision ON {schema}.iqc_item_measurements")
    op.execute(f"DROP TRIGGER iqc_item_fact_revision ON {schema}.iqc_inspection_items")
    op.execute(f"DROP FUNCTION {schema}.iqc_revise_from_detail()")
    op.execute(f"DROP TRIGGER iqc_fact_revision_guard ON {schema}.iqc_inspections")
    op.execute(f"DROP FUNCTION {schema}.iqc_fact_revision_guard()")
    op.drop_constraint("uq_iqc_inspection_factory", "iqc_inspections", type_="unique")
    op.drop_column("iqc_inspections", "inspection_revision")
    op.drop_column("iqc_inspections", "identity_generation")
