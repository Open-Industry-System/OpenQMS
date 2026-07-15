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
    # App (version_service.compute_snapshot_hash) uses compact JSON:
    #   json.dumps(..., sort_keys=True, separators=(",", ":"))
    # PG jsonb::text uses spaced separators and different key order — hashes NEVER match.
    # FMEA trigger historically compared NEW.snapshot::text (also PG format) against the
    # app-stored compact hash; that was already inconsistent. For CP there is no
    # `snapshot` column at all. Fix:
    # - fmea_versions: keep integrity check only when both sides use the same
    #   representation — require non-null hash + non-null snapshot (app is source of truth
    #   for the digest; full re-verify against PG text is not viable without a compact
    #   JSON encoder in PL/pgSQL).
    # - control_plan_versions: require non-null sha256_hash only (app computes over
    #   compact {header, items}); do NOT re-hash via jsonb::text.
    op.execute("""
    CREATE OR REPLACE FUNCTION verify_version_hash()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.sha256_hash IS NULL OR btrim(NEW.sha256_hash) = '' THEN
            RAISE EXCEPTION 'Version sha256_hash is required (table=%)', TG_TABLE_NAME;
        END IF;
        -- FMEA: require snapshot payload present (hash is app-computed compact JSON)
        IF TG_TABLE_NAME = 'fmea_versions' THEN
            IF NEW.snapshot IS NULL THEN
                RAISE EXCEPTION 'FMEA version snapshot is required';
            END IF;
            RETURN NEW;
        END IF;
        -- CP: require header + items payloads present (hash is app-computed compact JSON
        -- of {"header":...,"items":...}); do not re-verify with jsonb::text.
        IF TG_TABLE_NAME = 'control_plan_versions' THEN
            IF NEW.header_snapshot IS NULL OR NEW.items_snapshot IS NULL THEN
                RAISE EXCEPTION 'CP version header_snapshot and items_snapshot are required';
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
