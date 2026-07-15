"""Fix verify_version_hash for FMEA + CP with content-level integrity.

Revision ID: 20260715_cp_version_trigger
Revises: 20260714_doc_gate_drop_capa_uq
Create Date: 2026-07-15

Problems fixed:
1. Original 020 function referenced NEW.snapshot on control_plan_versions (column
   does not exist) → every CP version INSERT crashed.
2. Interim fix only checked non-empty hash (no content integrity).
3. App compact JSON hash ≠ PG jsonb::text hash.

Solution: trigger ALWAYS re-computes and STORES sha256_hash from the actual
JSONB columns using encode(digest(...::text,'sha256'),'hex') — same algorithm
as seed/test raw SQL inserts. App create_*_version helpers must use the same
DB-side digest (see version_service.compute_pg_jsonb_hash) so stored values
match. Downgrade restores a safe dual-table function (not the broken NEW.snapshot
on CP).
"""
from alembic import op


revision = "20260715_cp_version_trigger"
down_revision = "20260714_doc_gate_drop_capa_uq"
branch_labels = None
depends_on = None


_UPGRADE_FN = r"""
CREATE OR REPLACE FUNCTION verify_version_hash()
RETURNS TRIGGER AS $$
DECLARE
    payload jsonb;
    computed text;
BEGIN
    IF TG_TABLE_NAME = 'fmea_versions' THEN
        IF NEW.snapshot IS NULL THEN
            RAISE EXCEPTION 'FMEA version snapshot is required';
        END IF;
        payload := NEW.snapshot;
    ELSIF TG_TABLE_NAME = 'control_plan_versions' THEN
        IF NEW.header_snapshot IS NULL OR NEW.items_snapshot IS NULL THEN
            RAISE EXCEPTION 'CP version header_snapshot and items_snapshot are required';
        END IF;
        -- Canonical combined payload (must match app compute_pg_jsonb_hash for CP)
        payload := jsonb_build_object(
            'header', NEW.header_snapshot,
            'items', NEW.items_snapshot
        );
    ELSE
        RETURN NEW;
    END IF;

    computed := encode(digest(payload::text, 'sha256'), 'hex');
    -- Always store the content-bound hash (source of truth = JSONB columns)
    NEW.sha256_hash := computed;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_DOWNGRADE_FN = r"""
CREATE OR REPLACE FUNCTION verify_version_hash()
RETURNS TRIGGER AS $$
DECLARE
    payload jsonb;
    computed text;
BEGIN
    -- Safe dual-table implementation (same as upgrade) — never restore the
    -- broken NEW.snapshot-on-CP behaviour.
    IF TG_TABLE_NAME = 'fmea_versions' THEN
        IF NEW.snapshot IS NULL THEN
            RAISE EXCEPTION 'FMEA version snapshot is required';
        END IF;
        payload := NEW.snapshot;
    ELSIF TG_TABLE_NAME = 'control_plan_versions' THEN
        IF NEW.header_snapshot IS NULL OR NEW.items_snapshot IS NULL THEN
            RAISE EXCEPTION 'CP version header_snapshot and items_snapshot are required';
        END IF;
        payload := jsonb_build_object(
            'header', NEW.header_snapshot,
            'items', NEW.items_snapshot
        );
    ELSE
        RETURN NEW;
    END IF;
    computed := encode(digest(payload::text, 'sha256'), 'hex');
    NEW.sha256_hash := computed;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_FN)


def downgrade() -> None:
    # Keep a working dual-table function; do NOT restore broken NEW.snapshot on CP.
    op.execute(_DOWNGRADE_FN)
