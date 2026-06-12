"""add factory tables and nullable factory_id columns with backfill

Revision ID: 035_add_factory_tables_nullable
Revises: 20260611_add_review_reports
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "035_add_factory_tables_nullable"
down_revision: Union[str, None] = "20260611_add_review_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Create new tables ──────────────────────────────────────

    op.create_table(
        "factories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "user_factories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "factory_id", name="uq_user_factory"),
    )

    op.create_table(
        "supplier_shared_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("unified_credit_code", sa.String(30), unique=True, nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("short_name", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "group_kpi_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("kpi_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_kpi_snapshot_factory_date"),
    )

    op.create_table(
        "audit_program_target_factories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("program_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("audit_programs.program_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("program_id", "factory_id", name="uq_audit_program_factory"),
    )

    # ── Step 2: Insert seed factory ────────────────────────────────────

    op.execute(
        "INSERT INTO factories (id, code, name, is_active) "
        "VALUES (gen_random_uuid(), 'DEFAULT', '默认工厂', true)"
    )

    # Get the default factory ID for backfilling
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM factories WHERE code = 'DEFAULT'"))
    default_factory_id = str(result.fetchone()[0])

    # ── Step 3: Add factory_id to product_lines (NULLABLE) + backfill ───

    op.add_column("product_lines",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_product_lines_factory_id", "product_lines",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(
        f"UPDATE product_lines SET factory_id = '{default_factory_id}'"
    ))

    # ── Step 4: Add factory_id to users (NULLABLE) + backfill ───────────

    op.add_column("users",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_factory_id", "users",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(
        f"UPDATE users SET factory_id = '{default_factory_id}'"
    ))

    # ── Step 5: Backfill user_factories for existing users ──────────────

    op.execute(sa.text(f"""
        INSERT INTO user_factories (id, user_id, factory_id)
        SELECT gen_random_uuid(), user_id, '{default_factory_id}'
        FROM users
    """))

    # ── Step 6: Add factory_id to business tables (NULLABLE) + backfill ─
    #
    # Product-line-derived tables: backfill from product_lines.factory_id
    # via product_line_code (nullable → COALESCE with default_factory_id).

    # --- Tables with product_line_code (nullable) ---

    _pl_nullable_tables = [
        "fmea_documents", "capa_eightd", "control_plans",
        "iqc_materials", "iqc_inspections",
        "iqc_aql_configs", "iqc_aql_profiles",
        "quality_goals", "management_reviews",
        "audit_checklist_templates", "supplier_risk_configs",
        "supplier_risk_notification_channels",
    ]

    for tbl in _pl_nullable_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = COALESCE(
                (SELECT factory_id FROM product_lines
                 WHERE product_lines.code = {tbl}.product_line_code),
                '{default_factory_id}'
            )
        """))

    # --- SPC tables: inspection_characteristics uses 'product_line' column ---

    op.add_column("inspection_characteristics",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_inspection_characteristics_factory_id",
                          "inspection_characteristics", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE inspection_characteristics SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = inspection_characteristics.product_line),
            '{default_factory_id}'
        )
    """))

    # --- Tables with product_line_code (NOT NULL, no COALESCE needed) ---

    _pl_nonnull_tables = [
        "control_plan_items", "apqp_projects", "change_impact_analysis",
        "special_characteristics", "customers", "customer_complaints",
        "rma_records",
    ]

    for tbl in _pl_nonnull_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = (
                SELECT factory_id FROM product_lines
                WHERE product_lines.code = {tbl}.product_line_code
            )
        """))

    # --- SPC child tables (no product_line_code, derive from inspection_characteristics) ---

    _spc_child_tables = [
        "sample_batches", "sample_values", "spc_alarms",
        "control_limit_snapshots",
    ]

    for tbl in _spc_child_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])

    # Backfill SPC children from inspection_characteristics via characteristic_id
    op.execute(sa.text("""
        UPDATE sample_batches SET factory_id = (
            SELECT factory_id FROM inspection_characteristics ic
            WHERE ic.characteristic_id = sample_batches.characteristic_id
        )
    """))
    op.execute(sa.text("""
        UPDATE sample_values SET factory_id = (
            SELECT factory_id FROM sample_batches sb
            WHERE sb.batch_id = sample_values.batch_id
        )
    """))
    op.execute(sa.text("""
        UPDATE spc_alarms SET factory_id = (
            SELECT factory_id FROM inspection_characteristics ic
            WHERE ic.characteristic_id = spc_alarms.characteristic_id
        )
    """))
    op.execute(sa.text("""
        UPDATE control_limit_snapshots SET factory_id = (
            SELECT factory_id FROM inspection_characteristics ic
            WHERE ic.characteristic_id = control_limit_snapshots.characteristic_id
        )
    """))

    # --- MSA study tables with product_line_code (nullable) ---

    _msa_tables = [
        "grr_studies", "bias_studies", "linearity_studies",
        "stability_studies", "attribute_studies",
    ]

    for tbl in _msa_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = COALESCE(
                (SELECT factory_id FROM product_lines
                 WHERE product_lines.code = {tbl}.product_line_code),
                '{default_factory_id}'
            )
        """))

    # MSA measurement/result tables (no product_line_code, derive from study)
    op.add_column("grr_measurements",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_grr_measurements_factory_id", "grr_measurements",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE grr_measurements SET factory_id = (
            SELECT factory_id FROM grr_studies
            WHERE grr_studies.study_id = grr_measurements.study_id
        )
    """))

    op.add_column("grr_results",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_grr_results_factory_id", "grr_results",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE grr_results SET factory_id = (
            SELECT factory_id FROM grr_studies
            WHERE grr_studies.study_id = grr_results.study_id
        )
    """))

    op.add_column("bias_measurements",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_bias_measurements_factory_id", "bias_measurements",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE bias_measurements SET factory_id = (
            SELECT factory_id FROM bias_studies
            WHERE bias_studies.study_id = bias_measurements.study_id
        )
    """))

    op.add_column("bias_results",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_bias_results_factory_id", "bias_results",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE bias_results SET factory_id = (
            SELECT factory_id FROM bias_studies
            WHERE bias_studies.study_id = bias_results.study_id
        )
    """))

    op.add_column("linearity_measurements",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_linearity_measurements_factory_id",
                          "linearity_measurements", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE linearity_measurements SET factory_id = (
            SELECT factory_id FROM linearity_studies
            WHERE linearity_studies.study_id = linearity_measurements.study_id
        )
    """))

    op.add_column("linearity_results",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_linearity_results_factory_id",
                          "linearity_results", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE linearity_results SET factory_id = (
            SELECT factory_id FROM linearity_studies
            WHERE linearity_studies.study_id = linearity_results.study_id
        )
    """))

    op.add_column("stability_measurements",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_stability_measurements_factory_id",
                          "stability_measurements", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE stability_measurements SET factory_id = (
            SELECT factory_id FROM stability_studies
            WHERE stability_studies.study_id = stability_measurements.study_id
        )
    """))

    op.add_column("stability_results",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_stability_results_factory_id",
                          "stability_results", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE stability_results SET factory_id = (
            SELECT factory_id FROM stability_studies
            WHERE stability_studies.study_id = stability_results.study_id
        )
    """))

    op.add_column("attribute_measurements",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_attribute_measurements_factory_id",
                          "attribute_measurements", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE attribute_measurements SET factory_id = (
            SELECT factory_id FROM attribute_studies
            WHERE attribute_studies.study_id = attribute_measurements.study_id
        )
    """))

    op.add_column("attribute_results",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_attribute_results_factory_id",
                          "attribute_results", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE attribute_results SET factory_id = (
            SELECT factory_id FROM attribute_studies
            WHERE attribute_studies.study_id = attribute_results.study_id
        )
    """))

    # --- IQC child tables (no product_line_code, derive from parent) ---

    op.add_column("iqc_inspection_items",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_iqc_inspection_items_factory_id",
                          "iqc_inspection_items", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE iqc_inspection_items SET factory_id = (
            SELECT factory_id FROM iqc_inspections
            WHERE iqc_inspections.inspection_id = iqc_inspection_items.inspection_id
        )
    """))

    op.add_column("iqc_item_measurements",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_iqc_item_measurements_factory_id",
                          "iqc_item_measurements", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE iqc_item_measurements SET factory_id = (
            SELECT factory_id FROM iqc_inspection_items
            WHERE iqc_inspection_items.item_id = iqc_item_measurements.item_id
        )
    """))

    op.add_column("iqc_inspection_templates",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_iqc_inspection_templates_factory_id",
                          "iqc_inspection_templates", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE iqc_inspection_templates SET factory_id = (
            SELECT factory_id FROM iqc_materials
            WHERE iqc_materials.material_id = iqc_inspection_templates.material_id
        )
    """))

    op.add_column("iqc_template_items",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_iqc_template_items_factory_id",
                          "iqc_template_items", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE iqc_template_items SET factory_id = (
            SELECT factory_id FROM iqc_inspection_templates
            WHERE iqc_inspection_templates.template_id = iqc_template_items.template_id
        )
    """))

    op.add_column("iqc_aql_recommendations",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_iqc_aql_recommendations_factory_id",
                          "iqc_aql_recommendations", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE iqc_aql_recommendations SET factory_id = (
            SELECT factory_id FROM iqc_aql_profiles
            WHERE iqc_aql_profiles.profile_id = iqc_aql_recommendations.profile_id
        )
    """))

    op.add_column("iqc_aql_quality_snapshots",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_iqc_aql_quality_snapshots_factory_id",
                          "iqc_aql_quality_snapshots", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE iqc_aql_quality_snapshots SET factory_id = COALESCE(
            (SELECT factory_id FROM iqc_inspections
             WHERE iqc_inspections.inspection_id = iqc_aql_quality_snapshots.inspection_id),
            '{default_factory_id}'
        )
    """))

    # --- Gauges (nullable product_line_code) ---

    op.add_column("gauges",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_gauges_factory_id", "gauges",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE gauges SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = gauges.product_line_code),
            '{default_factory_id}'
        )
    """))

    op.add_column("gauge_calibrations",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_gauge_calibrations_factory_id", "gauge_calibrations",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE gauge_calibrations SET factory_id = (
            SELECT factory_id FROM gauges
            WHERE gauges.gauge_id = gauge_calibrations.gauge_id
        )
    """))

    # --- Document embedding + sync tables (nullable product_line_code) ---

    op.add_column("document_embeddings",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_document_embeddings_factory_id",
                          "document_embeddings", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE document_embeddings SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = document_embeddings.product_line_code),
            '{default_factory_id}'
        )
    """))

    op.add_column("embedding_sync_outbox",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_embedding_sync_outbox_factory_id",
                          "embedding_sync_outbox", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE embedding_sync_outbox SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = embedding_sync_outbox.product_line_code),
            '{default_factory_id}'
        )
    """))

    # --- Collaboration sessions (no product_line_code, default factory) ---

    op.add_column("collaboration_sessions",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_collaboration_sessions_factory_id",
                          "collaboration_sessions", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text(
        f"UPDATE collaboration_sessions SET factory_id = '{default_factory_id}'"
    ))

    # --- Recommendation cache (has product_line_code, NOT NULL) ---

    op.add_column("recommendation_cache",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_recommendation_cache_factory_id",
                          "recommendation_cache", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE recommendation_cache SET factory_id = (
            SELECT factory_id FROM product_lines
            WHERE product_lines.code = recommendation_cache.product_line_code
        )
    """))

    # --- CP validation tables (derive from control_plans) ---

    op.add_column("cp_validation_runs",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_cp_validation_runs_factory_id",
                          "cp_validation_runs", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE cp_validation_runs SET factory_id = (
            SELECT factory_id FROM control_plans
            WHERE control_plans.cp_id = cp_validation_runs.cp_id
        )
    """))

    op.add_column("cp_validation_findings",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_cp_validation_findings_factory_id",
                          "cp_validation_findings", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE cp_validation_findings SET factory_id = (
            SELECT factory_id FROM cp_validation_runs
            WHERE cp_validation_runs.run_id = cp_validation_findings.run_id
        )
    """))

    op.add_column("cp_validation_occurrences",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_cp_validation_occurrences_factory_id",
                          "cp_validation_occurrences", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE cp_validation_occurrences SET factory_id = (
            SELECT factory_id FROM cp_validation_findings
            WHERE cp_validation_findings.finding_id = cp_validation_occurrences.finding_id
        )
    """))

    # --- Review outputs (derive from management_reviews) ---

    op.add_column("review_outputs",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_review_outputs_factory_id",
                          "review_outputs", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE review_outputs SET factory_id = (
            SELECT factory_id FROM management_reviews
            WHERE management_reviews.review_id = review_outputs.review_id
        )
    """))

    # ── Step 7: Modify suppliers table ─────────────────────────────────

    # Add factory_id (NULLABLE) + backfill with default_factory_id
    op.add_column("suppliers",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_suppliers_factory_id", "suppliers",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(
        f"UPDATE suppliers SET factory_id = '{default_factory_id}'"
    ))

    # Add shared_profile_id (NULLABLE)
    op.add_column("suppliers",
                  sa.Column("shared_profile_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_suppliers_shared_profile_id", "suppliers",
                          "supplier_shared_profiles", ["shared_profile_id"], ["id"])

    # Drop old supplier_no unique constraint, add new composite (factory_id, supplier_no)
    op.drop_constraint("suppliers_supplier_no_key", "suppliers", type_="unique")
    op.create_unique_constraint("uq_supplier_no_per_factory", "suppliers",
                                ["factory_id", "supplier_no"])

    # ── Supplier sub-tables (derive from suppliers.factory_id) ─────────

    _supplier_child_tables = [
        "supplier_certifications", "supplier_evaluations",
        "supplier_ppap_submissions", "supplier_scars",
    ]

    for tbl in _supplier_child_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = (
                SELECT factory_id FROM suppliers
                WHERE suppliers.supplier_id = {tbl}.supplier_id
            )
        """))

    # Supplier risk alerts (derive from supplier_id -> suppliers.factory_id)
    op.add_column("supplier_risk_alerts",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_supplier_risk_alerts_factory_id",
                          "supplier_risk_alerts", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE supplier_risk_alerts SET factory_id = (
            SELECT factory_id FROM suppliers
            WHERE suppliers.supplier_id = supplier_risk_alerts.supplier_id
        )
    """))

    # ── Step 8: Add factory_id to audit_programs + audit_checklist_templates ──

    # audit_checklist_templates was already handled in Step 6 (nullable product_line_code)
    # Now add factory_id to audit_programs (nullable product_line_code)
    op.add_column("audit_programs",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_audit_programs_factory_id", "audit_programs",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE audit_programs SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = audit_programs.product_line_code),
            '{default_factory_id}'
        )
    """))

    # Audit child tables (derive from parent)
    op.add_column("audit_plans",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_audit_plans_factory_id", "audit_plans",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE audit_plans SET factory_id = (
            SELECT factory_id FROM audit_programs
            WHERE audit_programs.program_id = audit_plans.program_id
        )
    """))

    op.add_column("audit_findings",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_audit_findings_factory_id", "audit_findings",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE audit_findings SET factory_id = (
            SELECT factory_id FROM audit_plans
            WHERE audit_plans.audit_id = audit_findings.audit_id
        )
    """))

    # ── FMEA versions (derive from fmea_documents) ─────────────────────

    op.add_column("fmea_versions",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_fmea_versions_factory_id", "fmea_versions",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE fmea_versions SET factory_id = (
            SELECT factory_id FROM fmea_documents
            WHERE fmea_documents.fmea_id = fmea_versions.fmea_id
        )
    """))

    # ── Control plan versions (derive from control_plans) ──────────────

    op.add_column("control_plan_versions",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_control_plan_versions_factory_id",
                          "control_plan_versions", "factories",
                          ["factory_id"], ["id"])
    op.execute(sa.text("""
        UPDATE control_plan_versions SET factory_id = (
            SELECT factory_id FROM control_plans
            WHERE control_plans.cp_id = control_plan_versions.cp_id
        )
    """))

    # ── MES connection + sub-tables ────────────────────────────────────

    op.add_column("mes_connections",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_mes_connections_factory_id", "mes_connections",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE mes_connections SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = mes_connections.product_line_code),
            '{default_factory_id}'
        )
    """))

    # MES sub-tables with connection_id
    _mes_conn_tables = [
        "mes_production_orders", "mes_equipment_status",
        "mes_scrap_records", "mes_measurement_ingestions",
        "mes_sync_jobs", "mes_push_outbox",
        "mes_scrap_monthly_summary", "mes_production_orders_archive",
    ]

    for tbl in _mes_conn_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = (
                SELECT factory_id FROM mes_connections
                WHERE mes_connections.connection_id = {tbl}.connection_id
            )
        """))

    # ── PLM connection + sub-tables ────────────────────────────────────

    op.add_column("plm_connections",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_plm_connections_factory_id", "plm_connections",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE plm_connections SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = plm_connections.product_line_code),
            '{default_factory_id}'
        )
    """))

    _plm_conn_tables = [
        "plm_parts", "plm_boms", "plm_change_orders",
        "plm_sync_jobs", "plm_push_outbox",
        "plm_change_impact_tasks", "plm_part_fmea_links", "plm_part_sc_links",
    ]

    for tbl in _plm_conn_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = (
                SELECT factory_id FROM plm_connections
                WHERE plm_connections.connection_id = {tbl}.connection_id
            )
        """))

    # ── ERP connection + sub-tables ────────────────────────────────────

    op.add_column("erp_connections",
                  sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_erp_connections_factory_id", "erp_connections",
                          "factories", ["factory_id"], ["id"])
    op.execute(sa.text(f"""
        UPDATE erp_connections SET factory_id = COALESCE(
            (SELECT factory_id FROM product_lines
             WHERE product_lines.code = erp_connections.product_line_code),
            '{default_factory_id}'
        )
    """))

    _erp_conn_tables = [
        "erp_suppliers", "erp_customers", "erp_materials", "erp_locations",
        "erp_purchase_orders", "erp_sales_orders", "erp_inventory_balances",
        "erp_shipments", "erp_cost_records",
        "erp_sync_jobs", "erp_push_outbox",
    ]

    for tbl in _erp_conn_tables:
        op.add_column(tbl,
                      sa.Column("factory_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{tbl}_factory_id", tbl,
                              "factories", ["factory_id"], ["id"])
        op.execute(sa.text(f"""
            UPDATE {tbl} SET factory_id = (
                SELECT factory_id FROM erp_connections
                WHERE erp_connections.connection_id = {tbl}.connection_id
            )
        """))


def downgrade() -> None:
    # Remove factory_id from all business tables in reverse order

    # --- ERP sub-tables ---
    for tbl in [
        "erp_suppliers", "erp_customers", "erp_materials", "erp_locations",
        "erp_purchase_orders", "erp_sales_orders", "erp_inventory_balances",
        "erp_shipments", "erp_cost_records",
        "erp_sync_jobs", "erp_push_outbox",
    ]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    op.drop_constraint("fk_erp_connections_factory_id", "erp_connections", type_="foreignkey")
    op.drop_column("erp_connections", "factory_id")

    # --- PLM sub-tables ---
    for tbl in [
        "plm_parts", "plm_boms", "plm_change_orders",
        "plm_sync_jobs", "plm_push_outbox",
        "plm_change_impact_tasks", "plm_part_fmea_links", "plm_part_sc_links",
    ]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    op.drop_constraint("fk_plm_connections_factory_id", "plm_connections", type_="foreignkey")
    op.drop_column("plm_connections", "factory_id")

    # --- MES sub-tables ---
    for tbl in [
        "mes_production_orders", "mes_equipment_status",
        "mes_scrap_records", "mes_measurement_ingestions",
        "mes_sync_jobs", "mes_push_outbox",
        "mes_scrap_monthly_summary", "mes_production_orders_archive",
    ]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    op.drop_constraint("fk_mes_connections_factory_id", "mes_connections", type_="foreignkey")
    op.drop_column("mes_connections", "factory_id")

    # --- Control plan versions ---
    op.drop_constraint("fk_control_plan_versions_factory_id", "control_plan_versions", type_="foreignkey")
    op.drop_column("control_plan_versions", "factory_id")

    # --- FMEA versions ---
    op.drop_constraint("fk_fmea_versions_factory_id", "fmea_versions", type_="foreignkey")
    op.drop_column("fmea_versions", "factory_id")

    # --- Audit child tables ---
    op.drop_constraint("fk_audit_findings_factory_id", "audit_findings", type_="foreignkey")
    op.drop_column("audit_findings", "factory_id")

    op.drop_constraint("fk_audit_plans_factory_id", "audit_plans", type_="foreignkey")
    op.drop_column("audit_plans", "factory_id")

    op.drop_constraint("fk_audit_programs_factory_id", "audit_programs", type_="foreignkey")
    op.drop_column("audit_programs", "factory_id")

    # --- Supplier sub-tables + alerts ---
    for tbl in ["supplier_certifications", "supplier_evaluations",
                "supplier_ppap_submissions", "supplier_scars", "supplier_risk_alerts"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- Suppliers: restore original unique constraint ---
    op.drop_constraint("uq_supplier_no_per_factory", "suppliers", type_="unique")
    op.create_unique_constraint("suppliers_supplier_no_key", "suppliers", ["supplier_no"])
    op.drop_constraint("fk_suppliers_shared_profile_id", "suppliers", type_="foreignkey")
    op.drop_column("suppliers", "shared_profile_id")
    op.drop_constraint("fk_suppliers_factory_id", "suppliers", type_="foreignkey")
    op.drop_column("suppliers", "factory_id")

    # --- Review outputs ---
    op.drop_constraint("fk_review_outputs_factory_id", "review_outputs", type_="foreignkey")
    op.drop_column("review_outputs", "factory_id")

    # --- CP validation tables ---
    for tbl in ["cp_validation_occurrences", "cp_validation_findings", "cp_validation_runs"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- Recommendation cache ---
    op.drop_constraint("fk_recommendation_cache_factory_id", "recommendation_cache", type_="foreignkey")
    op.drop_column("recommendation_cache", "factory_id")

    # --- Collaboration sessions ---
    op.drop_constraint("fk_collaboration_sessions_factory_id", "collaboration_sessions", type_="foreignkey")
    op.drop_column("collaboration_sessions", "factory_id")

    # --- Embedding tables ---
    op.drop_constraint("fk_embedding_sync_outbox_factory_id", "embedding_sync_outbox", type_="foreignkey")
    op.drop_column("embedding_sync_outbox", "factory_id")

    op.drop_constraint("fk_document_embeddings_factory_id", "document_embeddings", type_="foreignkey")
    op.drop_column("document_embeddings", "factory_id")

    # --- Gauges ---
    op.drop_constraint("fk_gauge_calibrations_factory_id", "gauge_calibrations", type_="foreignkey")
    op.drop_column("gauge_calibrations", "factory_id")

    op.drop_constraint("fk_gauges_factory_id", "gauges", type_="foreignkey")
    op.drop_column("gauges", "factory_id")

    # --- IQC AQL tables ---
    op.drop_constraint("fk_iqc_aql_quality_snapshots_factory_id", "iqc_aql_quality_snapshots", type_="foreignkey")
    op.drop_column("iqc_aql_quality_snapshots", "factory_id")

    op.drop_constraint("fk_iqc_aql_recommendations_factory_id", "iqc_aql_recommendations", type_="foreignkey")
    op.drop_column("iqc_aql_recommendations", "factory_id")

    # --- IQC template tables ---
    op.drop_constraint("fk_iqc_template_items_factory_id", "iqc_template_items", type_="foreignkey")
    op.drop_column("iqc_template_items", "factory_id")

    op.drop_constraint("fk_iqc_inspection_templates_factory_id", "iqc_inspection_templates", type_="foreignkey")
    op.drop_column("iqc_inspection_templates", "factory_id")

    # --- IQC item tables ---
    op.drop_constraint("fk_iqc_item_measurements_factory_id", "iqc_item_measurements", type_="foreignkey")
    op.drop_column("iqc_item_measurements", "factory_id")

    op.drop_constraint("fk_iqc_inspection_items_factory_id", "iqc_inspection_items", type_="foreignkey")
    op.drop_column("iqc_inspection_items", "factory_id")

    # --- MSA measurement/result tables ---
    for tbl in ["grr_measurements", "grr_results",
                "bias_measurements", "bias_results",
                "linearity_measurements", "linearity_results",
                "stability_measurements", "stability_results",
                "attribute_measurements", "attribute_results"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- MSA study tables ---
    for tbl in ["grr_studies", "bias_studies", "linearity_studies",
                "stability_studies", "attribute_studies"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- SPC child tables ---
    for tbl in ["sample_batches", "sample_values", "spc_alarms", "control_limit_snapshots"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- inspection_characteristics ---
    op.drop_constraint("fk_inspection_characteristics_factory_id", "inspection_characteristics", type_="foreignkey")
    op.drop_column("inspection_characteristics", "factory_id")

    # --- product_line_code NOT NULL tables ---
    for tbl in ["control_plan_items", "apqp_projects", "change_impact_analysis",
                "special_characteristics", "customers", "customer_complaints",
                "rma_records"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- product_line_code nullable tables ---
    for tbl in ["fmea_documents", "capa_eightd", "control_plans",
                "iqc_materials", "iqc_inspections",
                "iqc_aql_configs", "iqc_aql_profiles",
                "quality_goals", "management_reviews",
                "audit_checklist_templates", "supplier_risk_configs",
                "supplier_risk_notification_channels"]:
        op.drop_constraint(f"fk_{tbl}_factory_id", tbl, type_="foreignkey")
        op.drop_column(tbl, "factory_id")

    # --- users ---
    op.drop_constraint("fk_users_factory_id", "users", type_="foreignkey")
    op.drop_column("users", "factory_id")

    # --- product_lines ---
    op.drop_constraint("fk_product_lines_factory_id", "product_lines", type_="foreignkey")
    op.drop_column("product_lines", "factory_id")

    # --- Drop new tables ---
    op.drop_table("audit_program_target_factories")
    op.drop_table("group_kpi_snapshots")
    op.drop_table("supplier_shared_profiles")
    op.drop_table("user_factories")
    op.drop_table("factories")