"""i18n: convert capa severity and audit customer_type from Chinese to codes

Revision ID: 20260615_i18n_severity_ctype
Revises: 20260615_i18n_sc_category_codes
Create Date: 2026-06-15

Note: customer_complaints.severity is intentionally left as Chinese literals —
the backend VALID_SEVERITIES validator and dashboard counting logic depend on
those values, and the frontend reverse-maps them for display. Only capa_eightd
severity (no backend validator; frontend already expects codes) is converted.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260615_i18n_severity_ctype"
down_revision: Union[str, None] = "20260615_i18n_sc_category_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CAPA 8D severity: Chinese labels -> language-independent codes.
    op.execute("UPDATE capa_eightd SET severity = 'fatal' WHERE severity = '致命'")
    op.execute("UPDATE capa_eightd SET severity = 'serious' WHERE severity = '严重'")
    op.execute("UPDATE capa_eightd SET severity = 'general' WHERE severity = '一般'")
    op.execute("UPDATE capa_eightd SET severity = 'minor' WHERE severity = '轻微'")
    # Customer audit customer_type: only the "other" option was stored in Chinese.
    op.execute("UPDATE audit_plans SET customer_type = 'other' WHERE customer_type = '其他'")


def downgrade() -> None:
    op.execute("UPDATE audit_plans SET customer_type = '其他' WHERE customer_type = 'other'")
    op.execute("UPDATE capa_eightd SET severity = '轻微' WHERE severity = 'minor'")
    op.execute("UPDATE capa_eightd SET severity = '一般' WHERE severity = 'general'")
    op.execute("UPDATE capa_eightd SET severity = '严重' WHERE severity = 'serious'")
    op.execute("UPDATE capa_eightd SET severity = '致命' WHERE severity = 'fatal'")
