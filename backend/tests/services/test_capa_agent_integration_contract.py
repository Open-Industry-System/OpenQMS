"""Pure reconciliation contracts; database I/O is confined to an in-memory boundary."""
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import settings
from app.core.permissions import Module
from app.core.tenant_transaction import TenantBinding, TenantUnavailable, bind_business_transaction
from app.services.capa_agent_projection import build_masked_d4_projection, projection_digest


class SnapshotEngine:
    def __init__(self, binding, *, generation=None):
        self.binding = binding
        self.generation = binding.generation if generation is None else generation
        self.calls = []
        self.capa = SimpleNamespace(report_id=uuid4(), document_no="8D-CONTRACT", status="D4_ROOT_CAUSE",
            severity="major", factory_id=uuid4(), product_line_code="LINE",
            updated_at=datetime(2026, 11, 3, tzinfo=UTC), title="SECRET", d4_root_cause="SECRET")
        self.child = SimpleNamespace(verification_id=uuid4(), conclusion="pending", is_verified=False,
                                     root_cause_text="SECRET", evidence_attachments=["SECRET"])

    @asynccontextmanager
    async def connect(self):
        self.calls.append("connect")
        yield self

    @asynccontextmanager
    async def begin(self):
        yield self

    async def run_sync(self, fn, binding):
        assert fn is bind_business_transaction
        self.calls.append("bind")
        outer = self

        class Registry:
            def scalar(self, statement, params):
                return True

            def execute(self, statement, params):
                assert params["tenant_id"] == binding.tenant_id
                return SimpleNamespace(one_or_none=lambda: SimpleNamespace(status="active",
                    generation=outer.generation, schema_name=outer.binding.schema_name))

            def exec_driver_sql(self, path):
                assert binding.schema_name in path
                assert "public" not in path

        fn(Registry(), binding)

    async def execute(self, statement):
        if str(statement).startswith("SET TRANSACTION"):
            self.calls.append(str(statement))
            return None
        columns = tuple(statement.selected_columns.keys())
        self.calls.append(columns)
        if "report_id" in columns:
            assert columns == ("report_id", "document_no", "status", "severity", "factory_id", "product_line_code", "updated_at")
            return SimpleNamespace(one_or_none=lambda: self.capa)
        assert columns == ("verification_id", "conclusion", "is_verified")
        # Both report and factory predicates must constrain the child read.
        assert "capa_id" in str(statement) and "factory_id" in str(statement)
        return SimpleNamespace(all=lambda: [self.child])


@pytest.mark.asyncio
async def test_bound_snapshot_preserves_main_allowlist_and_feature_tenant_order(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    binding = TenantBinding(uuid4(), "tenant_contract", 7, "business")
    engine = SnapshotEngine(binding)
    result = await build_masked_d4_projection(engine.capa.report_id, binding=binding, engine=engine)
    assert engine.calls[:3] == ["connect", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", "bind"]
    assert set(result) == {"projection_id", "source_capa_id", "data_class", "report_id", "document_no",
        "status", "severity", "factory_id", "product_line_code", "updated_at", "verifications", "projection_digest"}
    assert result["verifications"] == [{"verification_id": str(engine.child.verification_id),
                                        "conclusion": "pending", "is_verified": False}]
    assert "SECRET" not in str(result)
    assert result["projection_digest"] == projection_digest({k: v for k, v in result.items() if k != "projection_digest"})


@pytest.mark.asyncio
async def test_changed_generation_refuses_before_reading_business_columns(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    binding = TenantBinding(uuid4(), "tenant_contract", 7, "business")
    engine = SnapshotEngine(binding, generation=8)
    with pytest.raises(TenantUnavailable):
        await build_masked_d4_projection(uuid4(), binding=binding, engine=engine)
    assert engine.calls == ["connect", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", "bind"]


@pytest.mark.asyncio
@pytest.mark.parametrize("binding_kind", ["missing", "maintenance"])
async def test_no_public_fallback_or_maintenance_binding(monkeypatch, binding_kind):
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    binding = TenantBinding(uuid4(), "tenant_contract", 7, "maintenance")
    engine = SnapshotEngine(binding)
    with pytest.raises(TenantUnavailable):
        await build_masked_d4_projection(uuid4(), binding=None if binding_kind == "missing" else binding, engine=engine)
    assert engine.calls == []


def test_cross_module_source_revocation_refuses_the_whole_derived_package():
    from app.services.agent.permissions.delivery import SourceLabel, can_view_derived, derive_label

    sources = (SourceLabel(Module.CAPA, uuid4(), "internal", "capa.d4.summary.masked.v1", "masked", "v1"),
               SourceLabel(Module.FMEA, uuid4(), "restricted", "fmea.source.raw.v1", "raw", "v2"))
    label = derive_label(sources)
    current = frozenset((s.owner, s.object_id, s.capability_id, s.projection) for s in sources)
    assert can_view_derived(label, True, current)
    assert label.sensitivity == "restricted"
    assert not can_view_derived(label, True, frozenset({next(iter(current))}))
    assert not can_view_derived(label, False, current)


@pytest.mark.asyncio
async def test_runtime_off_rejects_even_invalid_body_and_tenant_before_database(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/agent/tasks", content=b"invalid-json",
                                     headers={"X-Tenant-ID": "invalid-tenant"})
    assert response.status_code == 404
