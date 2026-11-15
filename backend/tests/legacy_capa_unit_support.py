"""Opt-in adapters for existing prompt/orchestration tests with inert DB doubles.

Imported explicitly by those unit files. Real SQLAlchemy sessions always run
the production authority queries; R6 security acceptance does not import this.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def legacy_material_unit_guards(monkeypatch):
    from app.services import capa_d4_material, capa_current_access, capa_draft_service

    def adapt(module, name, fake):
        original = getattr(module, name)
        async def current(db, *args, **kwargs):
            if not isinstance(db, AsyncSession):
                return fake
            return await original(db, *args, **kwargs)
        monkeypatch.setattr(module, name, current)

    adapt(capa_d4_material, 'require_current_egress_statement', None)
    adapt(capa_d4_material, 'require_legacy_context', None)
    adapt(capa_d4_material, 'require_legacy_root_only', None)
    adapt(capa_d4_material, 'legacy_recommendation_binding', 'unit-legacy-material')
    adapt(capa_d4_material, 'capture_legacy_candidate_bindings', ())
    adapt(capa_d4_material, 'require_legacy_candidate_bindings', None)
    adapt(capa_d4_material, 'material_version', 'unit-legacy-material')
    adapt(capa_current_access, 'current_capa_actor_access', (SimpleNamespace(), SimpleNamespace()))
    adapt(capa_current_access, 'current_capa_target_metadata', SimpleNamespace())
    adapt(capa_draft_service, '_capture_fmea_context_bindings', ())
    adapt(capa_draft_service, '_require_fmea_context_bindings', None)
    recipient = capa_draft_service._recipient_binding
    monkeypatch.setattr(capa_draft_service, '_recipient_binding',
        lambda pc: recipient(pc) or 'unit-controlled-receiver')
    capa_draft_service._in_flight_bindings.clear()
