"""Migration tests for supplier_risk_capa_inputs + capa_eightd.supplier_id (US-E2E-01.6)."""
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

REV = "20260716_supplier_risk_capa_inputs"
HEAD = "20260716_seed_r11_config"
MERGE = "20260716_merge_scar_and_doc_gate"


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _sync_engine(mig_url: str):
    return create_engine(mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))


def test_migration_creates_supplier_risk_capa_inputs(mig_db_url):
    """Empty DB upgrade head creates supplier_risk_capa_inputs + capa_eightd.supplier_id."""
    command.upgrade(_cfg(mig_db_url), "head")
    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        table_exists = conn.execute(sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema='public' AND table_name='supplier_risk_capa_inputs'"
            ")"
        )).scalar()
        assert table_exists is True

        cols = {
            r[0]
            for r in conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='supplier_risk_capa_inputs'"
            ))
        }
        for required in (
            "input_id",
            "capa_id",
            "supplier_id",
            "factory_id",
            "product_line_code",
            "created_by",
            "severity",
            "disposition",
            "repeat_suggested",
            "repeat_detection_status",
            "repeat_confirmed",
            "matched_capa_nos",
            "evaluated_risk_level",
            "evaluated_risk_score",
            "evaluated_at",
            "status",
            "linked_alert_id",
            "attempt_count",
            "max_attempts",
            "last_error",
            "next_retry_at",
            "locked_at",
            "claim_token",
            "created_at",
            "updated_at",
        ):
            assert required in cols, f"missing column {required}"

        capa_supplier = conn.execute(sa.text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='capa_eightd' AND column_name='supplier_id'"
        )).one_or_none()
        assert capa_supplier is not None
        assert capa_supplier[0] == "uuid"
        assert capa_supplier[1] == "YES"

        idx = conn.execute(sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname='public' AND indexname='ix_risk_input_status_retry'"
        )).scalar()
        assert idx == 1
    engine.dispose()


def test_upgrade_normalizes_empty_rule_results(mig_db_url):
    """Historical supplier_risk_alerts.rule_results '{}' become '[]'; non-empty lists stay."""
    command.upgrade(_cfg(mig_db_url), MERGE)
    engine = _sync_engine(mig_db_url)

    alert_empty = str(uuid.uuid4())
    alert_list = str(uuid.uuid4())
    fid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    sid = str(uuid.uuid4())

    with engine.connect() as conn:
        with conn.begin():
            role_id = conn.execute(sa.text("SELECT id FROM role_definitions LIMIT 1")).scalar()
            if role_id is None:
                role_id = str(uuid.uuid4())
                conn.execute(sa.text(
                    "INSERT INTO role_definitions (id, role_key, name_zh, name_en, is_system) "
                    f"VALUES ('{role_id}', 'test', 'test', 'test', true)"
                ))
            conn.execute(sa.text(
                f"INSERT INTO factories (id, code, name) VALUES ('{fid}', 'F1', 'F1')"
            ))
            conn.execute(sa.text(
                "INSERT INTO users (user_id, username, password_hash, is_active, role_id, legacy_role, factory_id) "
                f"VALUES ('{uid}', 'u1', 'x', true, '{role_id}', 'admin', '{fid}')"
            ))
            conn.execute(sa.text(
                "INSERT INTO suppliers (supplier_id, supplier_no, factory_id, name, short_name, created_by) "
                f"VALUES ('{sid}', 'SUP1', '{fid}', 'SUP1', 'S1', '{uid}')"
            ))
            # '{}' legacy shape — migration must normalize to []
            conn.execute(sa.text(
                "INSERT INTO supplier_risk_alerts ("
                "  alert_id, supplier_id, factory_id, risk_level, risk_score, "
                "  quality_score, delivery_score, compliance_score, rule_results, "
                "  alert_type, status, snapshot_date"
                ") VALUES ("
                f"  '{alert_empty}', '{sid}', '{fid}', 'high', 90, 90, 90, 90, "
                "  '{}'::jsonb, 'initial', 'open', DATE '2026-01-01'"
                ")"
            ))
            # Non-empty list must remain untouched (unique on supplier_id+snapshot_date)
            conn.execute(sa.text(
                "INSERT INTO supplier_risk_alerts ("
                "  alert_id, supplier_id, factory_id, risk_level, risk_score, "
                "  quality_score, delivery_score, compliance_score, rule_results, "
                "  alert_type, status, snapshot_date"
                ") VALUES ("
                f"  '{alert_list}', '{sid}', '{fid}', 'low', 10, 10, 10, 10, "
                "  '[{\"rule_id\":\"R1\"}]'::jsonb, 'initial', 'open', DATE '2026-01-02'"
                ")"
            ))
    engine.dispose()

    command.upgrade(_cfg(mig_db_url), REV)
    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        empty_val = conn.execute(sa.text(
            f"SELECT rule_results::text FROM supplier_risk_alerts WHERE alert_id='{alert_empty}'"
        )).scalar()
        assert empty_val == "[]"

        list_val = conn.execute(sa.text(
            f"SELECT rule_results::text FROM supplier_risk_alerts WHERE alert_id='{alert_list}'"
        )).scalar()
        assert list_val in ('[{"rule_id": "R1"}]', '[{"rule_id":"R1"}]')
    engine.dispose()


def test_single_alembic_head(mig_db_url):
    """Alembic reports a single head (all branches merged)."""
    from alembic.script import ScriptDirectory

    cfg = _cfg(mig_db_url)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    # Single head, currently 20260727_warranty_factory_id (extends
    # 20260726_add_cp_sync_outbox, which merged lateral_diffusion).
    assert heads == ["20260727_warranty_factory_id"], (
        f"expected single head 20260727_warranty_factory_id, got {heads}"
    )
