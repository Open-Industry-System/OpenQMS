"""seed r11 default config (no-op if R01 absent)

Revision ID: 20260716_seed_r11_config
Revises: 20260716_supplier_risk_capa_inputs
Create Date: 2026-07-16
"""
from alembic import op

revision = "20260716_seed_r11_config"
down_revision = "20260716_supplier_risk_capa_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op when R01 global configs are missing (empty/fresh DB).
    # Scope uniqueness is (rule_id, supplier_id, product_line_code) NULLS NOT DISTINCT,
    # so only one global R11 row is inserted (DISTINCT ON factory_id is unnecessary;
    # pick any R01 row's factory_id/updated_by).
    op.execute("""
        INSERT INTO supplier_risk_configs
          (config_id, rule_id, enabled, thresholds, weight, supplier_id, factory_id, category, product_line_code, updated_by, updated_at)
        SELECT gen_random_uuid(), 'R11', true,
               '{"base_score": 10, "severe_bonus": 10, "repeat_bonus": 10}'::jsonb,
               1.0, NULL, factory_id, 'quality', NULL, updated_by, NOW()
        FROM supplier_risk_configs
        WHERE rule_id = 'R01' AND supplier_id IS NULL AND product_line_code IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM supplier_risk_configs
            WHERE rule_id = 'R11' AND supplier_id IS NULL AND product_line_code IS NULL
          )
        LIMIT 1
    """)


def downgrade() -> None:
    op.execute("DELETE FROM supplier_risk_configs WHERE rule_id = 'R11'")
