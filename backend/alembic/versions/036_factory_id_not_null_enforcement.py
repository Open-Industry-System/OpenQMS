"""enforce NOT NULL on business factory_id columns

Revision ID: 036_factory_id_not_null_enforcement
Revises: 035_add_factory_tables_nullable
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "036_factory_id_not_null_enforcement"
down_revision: Union[str, None] = "035_add_factory_tables_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All tables that received factory_id in migration 035, EXCEPT users (stays nullable).
# users.factory_id is intentionally nullable: group-level users may have no default factory.
_BUSINESS_TABLES = [
    # Core ownership
    "product_lines",
    # Product-line-derived (nullable product_line_code)
    "fmea_documents", "capa_eightd", "control_plans",
    "iqc_materials", "iqc_inspections",
    "iqc_aql_configs", "iqc_aql_profiles",
    "quality_goals", "management_reviews",
    "audit_checklist_templates", "supplier_risk_configs",
    "supplier_risk_notification_channels",
    # SPC
    "inspection_characteristics",
    "sample_batches", "sample_values", "spc_alarms", "control_limit_snapshots",
    # Product-line-derived (NOT NULL product_line_code)
    "control_plan_items", "apqp_projects", "change_impact_analysis",
    "special_characteristics", "customers", "customer_complaints",
    "rma_records",
    # MSA studies
    "grr_studies", "bias_studies", "linearity_studies",
    "stability_studies", "attribute_studies",
    # MSA measurements / results
    "grr_measurements", "grr_results",
    "bias_measurements", "bias_results",
    "linearity_measurements", "linearity_results",
    "stability_measurements", "stability_results",
    "attribute_measurements", "attribute_results",
    # IQC children
    "iqc_inspection_items", "iqc_item_measurements",
    "iqc_inspection_templates", "iqc_template_items",
    "iqc_aql_recommendations", "iqc_aql_quality_snapshots",
    # Gauges
    "gauges", "gauge_calibrations",
    # Embeddings
    "document_embeddings", "embedding_sync_outbox",
    # Collaboration
    "collaboration_sessions",
    # Recommendation cache
    "recommendation_cache",
    # CP validation
    "cp_validation_runs", "cp_validation_findings", "cp_validation_occurrences",
    # Review outputs
    "review_outputs",
    # Suppliers
    "suppliers",
    "supplier_certifications", "supplier_evaluations",
    "supplier_ppap_submissions", "supplier_scars",
    "supplier_risk_alerts",
    # Audit
    "audit_programs", "audit_plans", "audit_findings",
    # Versions
    "fmea_versions", "control_plan_versions",
    # MES
    "mes_connections",
    "mes_production_orders", "mes_equipment_status",
    "mes_scrap_records", "mes_measurement_ingestions",
    "mes_sync_jobs", "mes_push_outbox",
    "mes_scrap_monthly_summary", "mes_production_orders_archive",
    # PLM
    "plm_connections",
    "plm_parts", "plm_boms", "plm_change_orders",
    "plm_sync_jobs", "plm_push_outbox",
    "plm_change_impact_tasks", "plm_part_fmea_links", "plm_part_sc_links",
    # ERP
    "erp_connections",
    "erp_suppliers", "erp_customers", "erp_materials", "erp_locations",
    "erp_purchase_orders", "erp_sales_orders", "erp_inventory_balances",
    "erp_shipments", "erp_cost_records",
    "erp_sync_jobs", "erp_push_outbox",
]


def upgrade() -> None:
    # ── Step 1: Add indexes on factory_id for all business tables ────────
    for tbl in _BUSINESS_TABLES:
        op.create_index(
            f"ix_{tbl}_factory_id", tbl, ["factory_id"],
        )

    # ── Step 2: Enforce NOT NULL on factory_id for all business tables ───
    for tbl in _BUSINESS_TABLES:
        op.alter_column(tbl, "factory_id", nullable=False)


def downgrade() -> None:
    # ── Step 1: Remove NOT NULL constraint (make factory_id nullable) ────
    for tbl in _BUSINESS_TABLES:
        op.alter_column(tbl, "factory_id", nullable=True)

    # ── Step 2: Drop indexes ─────────────────────────────────────────────
    for tbl in _BUSINESS_TABLES:
        op.drop_index(f"ix_{tbl}_factory_id", table_name=tbl, if_exists=True)