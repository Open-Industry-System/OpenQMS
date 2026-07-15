"""Fix verify_version_hash() to handle both FMEA (snapshot) and CP
(header_snapshot+items_snapshot) version tables.

Revision ID: 20260715_cp_version_trigger
Revises: 20260714_doc_gate_drop_capa_uq
Create Date: 2026-07-15

The original 020 trigger function references NEW.snapshot unconditionally.
That column exists on fmea_versions but NOT on control_plan_versions (which
uses header_snapshot + items_snapshot), so every CP version INSERT raised
"record new has no field snapshot". The function now detects which columns
exist on NEW and verifies the combined CP snapshot when appropriate.
"""
from alembic import op


revision = "20260715_cp_version_trigger"
down_revision = "20260714_doc_gate_drop_capa_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION verify_version_hash()
    RETURNS TRIGGER AS $$
    DECLARE
        combined jsonb;
    BEGIN
        IF NEW.sha256_hash IS NULL THEN
            RETURN NEW;
        END IF;
        -- FMEA versions: single `snapshot` column
        IF TG_TABLE_NAME = 'fmea_versions' THEN
            IF NEW.snapshot IS NOT NULL
               AND NEW.sha256_hash != encode(digest(NEW.snapshot::text, 'sha256'), 'hex') THEN
                RAISE EXCEPTION 'Version snapshot hash mismatch: stored=%, computed=%',
                    NEW.sha256_hash, encode(digest(NEW.snapshot::text, 'sha256'), 'hex');
            END IF;
            RETURN NEW;
        END IF;
        -- Control plan versions: header_snapshot + items_snapshot combined
        IF TG_TABLE_NAME = 'control_plan_versions' THEN
            combined := jsonb_build_object(
                'header', COALESCE(NEW.header_snapshot, '{}'::jsonb),
                'items', COALESCE(NEW.items_snapshot, '[]'::jsonb)
            );
            IF NEW.sha256_hash != encode(digest(combined::text, 'sha256'), 'hex') THEN
                RAISE EXCEPTION 'CP version snapshot hash mismatch: stored=%, computed=%',
                    NEW.sha256_hash, encode(digest(combined::text, 'sha256'), 'hex');
            END IF;
            RETURN NEW;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION verify_version_hash()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.sha256_hash IS NOT NULL AND NEW.snapshot IS NOT NULL THEN
            IF NEW.sha256_hash != encode(digest(NEW.snapshot::text, 'sha256'), 'hex') THEN
                RAISE EXCEPTION 'Version snapshot hash mismatch: stored=%, computed=%',
                    NEW.sha256_hash, encode(digest(NEW.snapshot::text, 'sha256'), 'hex');
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
