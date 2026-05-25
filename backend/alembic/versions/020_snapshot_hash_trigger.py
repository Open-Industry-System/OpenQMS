"""add snapshot hash anti-tampering triggers on version tables

Revision ID: 020
Revises: 019
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Trigger: verify sha256_hash matches snapshot content on INSERT
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

    # Trigger: prevent UPDATE/DELETE on version records (immutable audit trail)
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_version_tampering()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'Version records are immutable and cannot be modified or deleted (table=%)',
            TG_TABLE_NAME;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # Apply hash verification on INSERT
    op.execute("""
    CREATE TRIGGER trg_fmea_version_hash_verify
        BEFORE INSERT ON fmea_versions
        FOR EACH ROW EXECUTE FUNCTION verify_version_hash();
    """)

    op.execute("""
    CREATE TRIGGER trg_cp_version_hash_verify
        BEFORE INSERT ON control_plan_versions
        FOR EACH ROW EXECUTE FUNCTION verify_version_hash();
    """)

    # Apply immutability protection on UPDATE/DELETE
    op.execute("""
    CREATE TRIGGER trg_fmea_version_no_update
        BEFORE UPDATE OR DELETE ON fmea_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_version_tampering();
    """)

    op.execute("""
    CREATE TRIGGER trg_cp_version_no_update
        BEFORE UPDATE OR DELETE ON control_plan_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_version_tampering();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_fmea_version_hash_verify ON fmea_versions")
    op.execute("DROP TRIGGER IF EXISTS trg_cp_version_hash_verify ON control_plan_versions")
    op.execute("DROP TRIGGER IF EXISTS trg_fmea_version_no_update ON fmea_versions")
    op.execute("DROP TRIGGER IF EXISTS trg_cp_version_no_update ON control_plan_versions")
    op.execute("DROP FUNCTION IF EXISTS verify_version_hash()")
    op.execute("DROP FUNCTION IF EXISTS prevent_version_tampering()")
