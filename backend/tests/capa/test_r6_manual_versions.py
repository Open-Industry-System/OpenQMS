"""Old clients cannot promote a pre-switch draft as a fresh manual edit."""
from uuid import uuid4
import pytest
from app.models.capa_r6 import CapaR6EntrySwitch
from tests.capa.r6_support import r6_case  # noqa: F401

@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_switched_put_requires_current_manual_epoch_and_material(r6_case):
    c = r6_case
    # A pre-existing switched deployment is fixture state, not a drain rehearsal.
    async with c.session() as db:
        db.add(CapaR6EntrySwitch(switch_id=uuid4(), epoch=1, state='switched',
            actor_id=c.actor().user_id, evidence={'fixture': 'already switched'}))
        await db.commit()
    before = await c.report()
    response = await c.actor().client.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': 'old preview'})
    assert response.status_code == 409, response.text
    assert (await c.report()).d4_root_cause == before.d4_root_cause
    detail = await c.actor().client.get(f'/api/capa/{c.report_id}')
    assert detail.status_code == 200, detail.text
    fresh = detail.json()
    assert fresh['entry_phase'] == 'switched' and fresh['entry_epoch'] == 1
    saved = await c.actor().client.put(f'/api/capa/{c.report_id}', json={
        'd4_root_cause':'fresh manual', 'expected_material_version':fresh['material_version'],
        'expected_entry_epoch':fresh['entry_epoch']})
    assert saved.status_code == 200, saved.text
    stale = await c.actor().client.put(f'/api/capa/{c.report_id}', json={
        'd4_root_cause':'stale overwrite','expected_material_version':fresh['material_version'],
        'expected_entry_epoch':fresh['entry_epoch']})
    assert stale.status_code == 409, stale.text
    assert (await c.report()).d4_root_cause == 'fresh manual'
