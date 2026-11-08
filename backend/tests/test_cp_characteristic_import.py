"""Authorized immutable PFMEA characteristic import against PostgreSQL."""
from copy import deepcopy
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.services.version_service import create_fmea_version

IDS = [f"00000000-0000-0000-0000-{n:012d}" for n in (101, 102, 201, 202, 203)]


def graph():
    return {
        "nodes": [
            {"id": "s1", "type": "ProcessStep", "process_number": "OP10", "name": "装配"},
            {"id": "w1", "type": "ProcessWorkElement", "classification": "Machine", "name": "装配机"},
            {"id": "sf1", "type": "ProcessStepFunction", "characteristics": [
                {"id": IDS[0], "kind": "product", "name": "孔距", "specification": "10±0.1"},
                {"id": IDS[1], "kind": "product", "name": "平面度"},
            ]},
            {"id": "wf1", "type": "ProcessWorkElementFunction", "characteristics": [
                {"id": IDS[2], "kind": "process", "name": "压力", "related_product_characteristic_ids": [IDS[0]]},
                {"id": IDS[3], "kind": "process", "name": "速度"},
                {"id": IDS[4], "kind": "process", "name": "时间"},
            ]},
        ],
        "edges": [
            {"source": "s1", "target": "sf1", "type": "HAS_FUNCTION"},
            {"source": "s1", "target": "w1", "type": "HAS_WORK_ELEMENT"},
            {"source": "w1", "target": "wf1", "type": "HAS_FUNCTION"},
        ],
    }


@pytest_asyncio.fixture
async def documents(db, admin_user, default_factory):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-{uuid.uuid4().hex[:8]}", title="Private source",
        factory_id=default_factory.id, product_line_code="DC-DC-100", fmea_type="PFMEA",
        status="approved", graph_data=graph(), created_by=admin_user.user_id,
    )
    cp = ControlPlan(
        cp_id=uuid.uuid4(), document_no=f"CP-{uuid.uuid4().hex[:8]}", title="Target",
        factory_id=default_factory.id, product_line_code="DC-DC-100", status="draft",
        created_by=admin_user.user_id,
    )
    db.add_all([fmea, cp])
    await db.flush()
    approved = await create_fmea_version(db, fmea, "approve", "Approved", admin_user.user_id)
    fmea.graph_data = {"nodes": [], "edges": []}
    fmea.status = "rework"
    await create_fmea_version(db, fmea, "manual", "Unapproved", admin_user.user_id)
    return cp, fmea, approved


def request(documents, **changes):
    cp, fmea, approved = documents
    body = {"fmea_id": str(fmea.fmea_id), "source_fmea_version_id": str(approved.version_id),
            "expected_lock_version": cp.lock_version, "step_ids": ["s1"]}
    body.update(changes)
    return body


async def preview(client, documents, **changes):
    return await client.post(f"/api/control-plans/{documents[0].cp_id}/import-from-fmea/preview",
                             json=request(documents, **changes))


async def apply(client, documents, result, **changes):
    body = request(documents, preview_digest=result["preview_digest"],
                   selected_candidate_keys=[i["candidate_key"] for i in result["items"]])
    body.update(changes)
    return await client.post(f"/api/control-plans/{documents[0].cp_id}/import-from-fmea", json=body)


async def rows(db, cp_id):
    return list((await db.scalars(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id)
                                 .order_by(ControlPlanItem.sort_order))).all())


@pytest.mark.asyncio
async def test_preview_apply_five_distinct_sources_and_repeat_keeps_item_ids(db, admin_client, documents):
    cp, _, approved_version = documents
    response = await preview(admin_client, documents)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['source_fmea_version_id'] == str(approved_version.version_id)
    assert len(result['items']) == 5
    assert all('candidate_key' in row for row in result['items'])
    assert [i['source_ref']['characteristic_id'] for i in result['items']] == IDS
    assert len({i['source_ref']['characteristic_id'] for i in result['items']}) == 5
    assert await rows(db, cp.cp_id) == []
    assert await db.scalar(select(func.count()).select_from(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id)) == 0
    assert cp.lock_version == 0 and cp.fmea_ref_id is None
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.record_id == cp.cp_id)) == 0
    accepted = await apply(admin_client, documents, result)
    assert accepted.status_code == 200, accepted.text
    created_items = await rows(db, cp.cp_id)
    assert len(created_items) == 5
    assert {row.source_fmea_node_id for row in created_items} == {'s1'}
    assert all(row.factory_id == cp.factory_id for row in created_items)
    assert [i.source_characteristic_ref['characteristic_id'] for i in created_items] == IDS
    assert all(i.source_characteristic_ref['accepted_source_version_id'] == str(approved_version.version_id) for i in created_items)
    assert all(i.evaluation_method is None and i.control_method is None and i.reaction_plan is None for i in created_items)
    original_ids = [i.item_id for i in created_items]
    assert cp.lock_version == 1 and cp.source_fmea_version_id == approved_version.version_id
    version = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id))
    assert version.source_fmea_version_id == approved_version.version_id
    assert [i['item_id'] for i in version.items_snapshot] == list(map(str, original_ids))
    assert [i['source_characteristic_ref']['characteristic_id'] for i in version.items_snapshot] == IDS
    assert (await apply(admin_client, documents, result, expected_lock_version=0)).status_code == 409
    again = await preview(admin_client, documents)
    assert again.status_code == 200, again.text
    assert all(i['action'] == 'existing' for i in again.json()['items'])
    assert (await apply(admin_client, documents, again.json())).status_code == 200
    assert [i.item_id for i in await rows(db, cp.cp_id)] == original_ids
    assert cp.lock_version == 1


@pytest.mark.asyncio
async def test_legacy_call_fails_closed_with_preview_guidance(admin_client, documents):
    response = await admin_client.post(f"/api/control-plans/{documents[0].cp_id}/import-from-fmea",
                                       json={"fmea_id": str(documents[1].fmea_id)})
    assert response.status_code == 409
    assert "preview" in response.text.lower() or "预览" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [
    {'preview_digest': 'forged'}, {'selected_candidate_keys': ['unknown']},
    {'selected_candidate_keys': []}, {'expected_lock_version': 77}, {'step_ids': []},
    {'step_ids': ['missing']}, {'step_ids': ['s1'], 'step_nos': ['OP10']},
])
async def test_stale_digest_and_invalid_selection_write_nothing(db, admin_client, documents, change):
    result = (await preview(admin_client, documents)).json()
    response = await apply(admin_client, documents, result, **change)
    assert response.status_code == 409, response.text
    assert await rows(db, documents[0].cp_id) == []
    assert documents[0].lock_version == 0


@pytest.mark.asyncio
async def test_server_derived_fields_not_client_display_are_imported(db, admin_client, documents):
    result = (await preview(admin_client, documents)).json()
    result['items'][0]['fields']['product_characteristic'] = 'forged display'
    response = await apply(admin_client, documents, result,
                           selected_candidate_keys=[result['items'][0]['candidate_key']])
    assert response.status_code == 200, response.text
    imported = await rows(db, documents[0].cp_id)
    assert len(imported) == 1 and imported[0].product_characteristic == '孔距'


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['approved_cp', 'changed_cp', 'source_factory', 'source_line', 'target_factory', 'target_line', 'other_version', 'unapproved_version', 'source_conflict', 'deleted_source'])
async def test_apply_rechecks_current_state_scope_and_source(db, admin_client, documents, default_factory, mutation):
    cp, fmea, approved = documents
    result = (await preview(admin_client, documents)).json()
    changes = {}
    if mutation == 'approved_cp':
        cp.status = 'approved'
    elif mutation == 'changed_cp':
        cp.lock_version += 1
    elif mutation.endswith('factory'):
        from app.models.factory import Factory
        other = Factory(id=uuid.uuid4(), code=uuid.uuid4().hex[:8], name='Private source')
        db.add(other)
        await db.flush()
        (fmea if mutation == 'source_factory' else cp).factory_id = other.id
    elif mutation.endswith('line'):
        from app.models.product_line import ProductLine
        code = uuid.uuid4().hex[:12]
        db.add(ProductLine(code=code, name='Other', factory_id=default_factory.id))
        await db.flush()
        (fmea if mutation == 'source_line' else cp).product_line_code = code
    elif mutation == 'other_version':
        other = FMEADocument(fmea_id=uuid.uuid4(), document_no=uuid.uuid4().hex, title='Private',
                             factory_id=default_factory.id, product_line_code='DC-DC-100', graph_data=graph())
        db.add(other)
        await db.flush()
        ver = await create_fmea_version(db, other, 'approve', '', None)
        changes['source_fmea_version_id'] = str(ver.version_id)
    elif mutation == 'unapproved_version':
        ver = await db.scalar(select(FMEAVersion).where(FMEAVersion.fmea_id == fmea.fmea_id, FMEAVersion.change_type == 'manual'))
        changes['source_fmea_version_id'] = str(ver.version_id)
    elif mutation == 'source_conflict':
        other = FMEADocument(fmea_id=uuid.uuid4(), document_no=uuid.uuid4().hex, title='Other', factory_id=default_factory.id)
        db.add(other)
        await db.flush()
        cp.fmea_ref_id = other.fmea_id
    elif mutation == 'deleted_source':
        changes['fmea_id'] = str(uuid.uuid4())
    await db.flush()
    response = await apply(admin_client, documents, result, **changes)
    assert response.status_code in (403, 404, 409), response.text
    assert 'Private source' not in response.text
    assert await rows(db, cp.cp_id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('selection', [{"step_ids": []}, {"step_ids": ["bad"]}, {"step_ids": None, "step_nos": []}])
async def test_preview_empty_unknown_selection_is_not_all(admin_client, documents, selection):
    response = await preview(admin_client, documents, **selection)
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy', [False, True])
async def test_legacy_snapshot_and_ambiguous_step_numbers_are_blocked(db, admin_client, documents, admin_user, legacy):
    _, fmea, _ = documents
    modified = graph()
    if legacy:
        del modified['nodes'][2]['characteristics']
    else:
        modified['nodes'].append({'id': 's2', 'type': 'ProcessStep', 'process_number': 'OP10'})
    fmea.graph_data = modified
    approved = await create_fmea_version(db, fmea, 'approve', '', admin_user.user_id)
    response = await preview(admin_client, documents, source_fmea_version_id=str(approved.version_id), step_ids=None, step_nos=['OP10'])
    if legacy:
        assert response.status_code == 200, response.text
        assert any(i['blocking'] and i['code'] == 'legacy_characteristics_missing' for i in response.json()['issues'])
        response = await apply(admin_client, documents, response.json(), source_fmea_version_id=str(approved.version_id), step_ids=None, step_nos=['OP10'])
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_unique_legacy_step_number_resolves_same_preview(admin_client, documents):
    by_id = (await preview(admin_client, documents)).json()
    by_no = await preview(admin_client, documents, step_ids=None, step_nos=['OP10'])
    assert by_no.status_code == 200, by_no.text
    assert by_no.json()['preview_digest'] == by_id['preview_digest']


@pytest.mark.asyncio
async def test_multiple_existing_control_rows_are_explicit_ambiguity(db, admin_client, documents):
    result = (await preview(admin_client, documents)).json()
    assert (await apply(admin_client, documents, result)).status_code == 200
    first = (await rows(db, documents[0].cp_id))[0]
    db.add(ControlPlanItem(cp_id=documents[0].cp_id, factory_id=documents[0].factory_id,
                           source_fmea_node_id='s1', source_characteristic_ref=deepcopy(first.source_characteristic_ref), sort_order=5))
    await db.flush()
    again = await preview(admin_client, documents)
    assert again.status_code == 200, again.text
    assert any(i['code'] == 'ambiguous_existing_rows' and i['blocking'] for i in again.json()['issues'])
    assert (await apply(admin_client, documents, again.json())).status_code == 409
    assert len(await rows(db, documents[0].cp_id)) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['planning', 'fmea', 'active', 'role', 'factory', 'product_line'])
async def test_revoked_authority_between_preview_and_apply(db, admin_client, documents, admin_user, revoke):
    from app.models.role import RoleDefinition, RolePermission, UserProductLine
    from app.models.user import User
    from app.models.factory import UserFactory
    from app.core.deps import RequestScope, get_request_scope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from app.main import app
    role = RoleDefinition(id=uuid.uuid4(), role_key=uuid.uuid4().hex[:20], name_zh='测试', name_en='Test', bypass_row_level_security=False)
    db.add(role)
    await db.flush()
    user = User(user_id=uuid.uuid4(), username=uuid.uuid4().hex, password_hash='not-used', legacy_role='viewer', role_id=role.id, factory_id=None)
    db.add(user)
    await db.flush()
    permissions = [RolePermission(role_id=role.id, module='planning', permission_level=2), RolePermission(role_id=role.id, module='fmea', permission_level=1)]
    factory_grant = UserFactory(user_id=user.user_id, factory_id=documents[0].factory_id)
    line_grant = UserProductLine(user_id=user.user_id, product_line_code='DC-DC-100')
    db.add_all([*permissions, factory_grant, line_grant])
    await db.flush()
    scope = RequestScope(FactoryScope([documents[0].factory_id], documents[0].factory_id), documents[0].factory_id, ProductLineScope('EXPLICIT', ['DC-DC-100']), user)
    app.dependency_overrides[get_request_scope] = lambda: scope
    before = await preview(admin_client, documents)
    assert before.status_code == 200, before.text
    if revoke in ('planning', 'fmea'):
        next(p for p in permissions if p.module == revoke).permission_level = 0
    elif revoke == 'active':
        user.is_active = False
    elif revoke == 'role':
        role.is_active = False
    else:
        await db.delete(factory_grant if revoke == 'factory' else line_grant)
    await db.flush()
    response = await apply(admin_client, documents, before.json())
    assert response.status_code in (403, 404), response.text
    assert 'Private source' not in response.text
    assert await rows(db, documents[0].cp_id) == []


@pytest.mark.asyncio
async def test_wrong_tenant_context_never_falls_back_to_public(admin_client, documents):
    from app.core.tenant_utils import current_tenant_schema
    token = current_tenant_schema.set('tenant_not_the_request_schema')
    try:
        response = await preview(admin_client, documents)
    finally:
        current_tenant_schema.reset(token)
    assert response.status_code == 404, response.text
    assert 'Private source' not in response.text


@pytest.mark.asyncio
async def test_second_insert_failure_rolls_back_items_header_audit_and_version(db, admin_client, documents):
    from sqlalchemy import event
    cp_id = documents[0].cp_id
    result = (await preview(admin_client, documents)).json()
    count = 0
    def fail_second(mapper, connection, target):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError('injected second insert')
    event.listen(ControlPlanItem, 'before_insert', fail_second)
    try:
        async with db.begin_nested():
            with pytest.raises(RuntimeError, match='injected second insert'):
                await apply(admin_client, documents, result)
    finally:
        event.remove(ControlPlanItem, 'before_insert', fail_second)
    assert count == 2
    assert await rows(db, cp_id) == []
    cp = await db.get(ControlPlan, cp_id, populate_existing=True)
    assert cp.lock_version == 0 and cp.fmea_ref_id is None and cp.source_fmea_version_id is None
    assert await db.scalar(select(func.count()).select_from(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp_id)) == 0
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.record_id == cp_id)) == 0


@pytest.mark.asyncio
async def test_stage_cp_version_does_not_commit_or_refresh(db, documents, admin_user, monkeypatch):
    from app.services import version_service
    calls = []
    async def forbidden(*args, **kwargs):
        calls.append('transaction boundary')
        raise AssertionError('stage must not commit/refresh')
    monkeypatch.setattr(db, 'commit', forbidden)
    monkeypatch.setattr(db, 'refresh', forbidden)
    version = await version_service.stage_cp_version(
        db, documents[0], 'import', 'staged', admin_user.user_id,
        source_fmea_version_id=documents[2].version_id,
    )
    assert calls == []
    assert version.version_id is not None
    assert version.source_fmea_version_id == documents[2].version_id
    assert await db.scalar(select(ControlPlanVersion.version_id).where(ControlPlanVersion.version_id == version.version_id)) == version.version_id


@pytest.mark.asyncio
async def test_version_stage_failure_after_row_insert_rolls_back_entire_import(db, admin_client, documents, monkeypatch):
    from app.services import control_plan_service
    result = (await preview(admin_client, documents)).json()
    cp_id = documents[0].cp_id
    async def fail_stage(session, *args, **kwargs):
        assert len(await rows(session, cp_id)) == 5
        raise RuntimeError('version stage failure')
    monkeypatch.setattr(control_plan_service, 'stage_cp_version', fail_stage)
    with pytest.raises(RuntimeError, match='version stage failure'):
        await apply(admin_client, documents, result)
    assert await rows(db, cp_id) == []
    cp = await db.get(ControlPlan, cp_id, populate_existing=True)
    assert cp.lock_version == 0 and cp.fmea_ref_id is None and cp.source_fmea_version_id is None
    assert await db.scalar(select(func.count()).select_from(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp_id)) == 0
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.record_id == cp_id)) == 0


@pytest.mark.asyncio
async def test_existing_cp_source_version_cannot_silently_rebind_other_document(db, admin_client, documents, default_factory):
    other = FMEADocument(fmea_id=uuid.uuid4(), document_no=uuid.uuid4().hex, title='Other source',
                         factory_id=default_factory.id, product_line_code='DC-DC-100', graph_data=graph())
    db.add(other)
    await db.flush()
    version = await create_fmea_version(db, other, 'approve', '', None)
    documents[0].source_fmea_version_id = version.version_id
    await db.flush()
    response = await preview(admin_client, documents)
    assert response.status_code == 409, response.text
    assert 'source_conflict' in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('mismatch', ['row_factory', 'row_source', 'legacy_row', 'version_factory'])
async def test_explicit_stored_source_and_factory_mismatches_reject(db, admin_client, documents, mismatch):
    from app.models.factory import Factory
    cp, fmea, version = documents
    result = (await preview(admin_client, documents)).json()
    other_factory = Factory(id=uuid.uuid4(), code=uuid.uuid4().hex[:10], name='Private')
    db.add(other_factory)
    await db.flush()
    changes = {}
    if mismatch == 'version_factory':
        bad = FMEAVersion(version_id=uuid.uuid4(), fmea_id=fmea.fmea_id, factory_id=other_factory.id,
                          major_no=7, minor_no=0, change_type='approve', snapshot=graph(), sha256_hash='trigger recomputes')
        db.add(bad)
        changes['source_fmea_version_id'] = str(bad.version_id)
    else:
        ref = deepcopy(result['items'][0]['source_ref'])
        if mismatch == 'row_source':
            ref['fmea_id'] = str(uuid.uuid4())
        db.add(ControlPlanItem(cp_id=cp.cp_id, factory_id=other_factory.id if mismatch == 'row_factory' else cp.factory_id,
                               source_fmea_node_id='s1', source_characteristic_ref=None if mismatch == 'legacy_row' else ref))
    await db.flush()
    response = await apply(admin_client, documents, result, **changes)
    assert response.status_code == 409, response.text
    assert len(await rows(db, cp.cp_id)) == (0 if mismatch == 'version_factory' else 1)
    assert cp.lock_version == 0


@pytest.mark.asyncio
async def test_digest_is_bound_to_target_cp_and_explicit_valid_step_selection(db, admin_client, documents, admin_user):
    cp, fmea, _ = documents
    modified = graph()
    modified['nodes'].append({'id': 's2', 'type': 'ProcessStep', 'process_number': 'OP20', 'name': 'Another'})
    fmea.graph_data = modified
    version = await create_fmea_version(db, fmea, 'approve', '', admin_user.user_id)
    changes = {'source_fmea_version_id': str(version.version_id)}
    before = (await preview(admin_client, documents, **changes)).json()
    wrong_step = await apply(admin_client, documents, before, **changes, step_ids=['s2'])
    assert wrong_step.status_code == 409
    other = ControlPlan(cp_id=uuid.uuid4(), document_no=uuid.uuid4().hex, title='Other CP',
                        factory_id=cp.factory_id, product_line_code=cp.product_line_code, status='draft')
    db.add(other)
    await db.flush()
    response = await admin_client.post(f'/api/control-plans/{other.cp_id}/import-from-fmea', json=request(
        documents, **changes, preview_digest=before['preview_digest'],
        selected_candidate_keys=[i['candidate_key'] for i in before['items']],
    ))
    assert response.status_code == 409
    assert await rows(db, cp.cp_id) == await rows(db, other.cp_id) == []


@pytest.mark.asyncio
async def test_import_preserves_reviewed_capa_material_and_cannot_satisfy_modify_delete(db, admin_client, documents, admin_user):
    from app.services.capa_doc_gate_service import _compute_diff, _match_key_point
    from app.services.version_service import create_cp_version, verify_cp_version
    cp, _, _ = documents
    result = (await preview(admin_client, documents)).json()
    reviewed_id = uuid.uuid4()
    old_ref = deepcopy(result['items'][0]['source_ref'])
    db.add(ControlPlanItem(item_id=reviewed_id, cp_id=cp.cp_id, factory_id=cp.factory_id,
                           product_characteristic='Reviewed product', control_method='Reviewed method',
                           reaction_plan='Reviewed reaction', source_fmea_node_id='s1',
                           source_characteristic_ref=old_ref, sort_order=0))
    await db.flush()
    baseline = await create_cp_version(db, cp, 'manual', 'Reviewed material', admin_user.user_id)
    baseline_items = deepcopy(baseline.items_snapshot)
    baseline_hash = baseline.sha256_hash
    before = (await preview(admin_client, documents)).json()
    assert any(i['code'] == 'existing_source_requires_sync' for i in before['issues'])
    item = await db.get(ControlPlanItem, reviewed_id)
    item.sample_size = 'Reviewed sample'
    await db.flush()
    assert (await apply(admin_client, documents, before)).status_code == 409
    before = (await preview(admin_client, documents)).json()
    response = await apply(admin_client, documents, before)
    assert response.status_code == 200, response.text
    current = await db.get(ControlPlanItem, reviewed_id, populate_existing=True)
    assert current.control_method == 'Reviewed method' and current.reaction_plan == 'Reviewed reaction'
    assert current.source_characteristic_ref == old_ref and current.product_characteristic == 'Reviewed product'
    latest = await db.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp.cp_id).order_by(ControlPlanVersion.minor_no.desc()))
    diff = _compute_diff('control_plan', {'header': baseline.header_snapshot, 'items': baseline_items}, latest)
    assert diff['items']['deleted_items'] == []
    for action in ('modify', 'delete'):
        kp = {'target_kind': 'cp_item', 'expected_action': action, 'target_key': str(reviewed_id), 'field': 'control_method'}
        assert _match_key_point(kp, diff, latest, 'control_plan') is False
    assert baseline.items_snapshot == baseline_items and baseline.sha256_hash == baseline_hash
    assert await verify_cp_version(db, baseline.version_id)


@pytest.mark.asyncio
async def test_cp_read_exposes_expected_lock_for_preview(admin_client, documents):
    response = await admin_client.get(f'/api/control-plans/{documents[0].cp_id}')
    assert response.status_code == 200, response.text
    assert response.json()['lock_version'] == 0


@pytest.mark.asyncio
async def test_same_named_two_factory_sources_never_mix_characteristic_relations(db, admin_client, documents, admin_user):
    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    from app.core.deps import get_request_scope, RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from app.main import app
    cp, source_a, version_a = documents
    factory_b = Factory(id=uuid.uuid4(), code=uuid.uuid4().hex[:10], name='Same name')
    db.add(factory_b)
    await db.flush()
    line_b = uuid.uuid4().hex[:12]
    db.add(ProductLine(code=line_b, name='Other line', factory_id=factory_b.id))
    other_graph = graph()
    other_graph['nodes'][2]['characteristics'][0]['name'] = 'Other factory private product'
    source_b = FMEADocument(fmea_id=uuid.uuid4(), document_no=uuid.uuid4().hex, title=source_a.title,
                            factory_id=factory_b.id, product_line_code=line_b,
                            fmea_type='PFMEA', graph_data=other_graph)
    db.add(source_b)
    await db.flush()
    version_b = await create_fmea_version(db, source_b, 'approve', '', admin_user.user_id)
    scope = RequestScope(FactoryScope(None, cp.factory_id), None, ProductLineScope('ALL', None), admin_user)
    app.dependency_overrides[get_request_scope] = lambda: scope
    response = await preview(admin_client, documents, fmea_id=str(source_b.fmea_id), source_fmea_version_id=str(version_b.version_id))
    assert response.status_code == 409 and 'Other factory private product' not in response.text
    wrong_version = await preview(admin_client, documents, source_fmea_version_id=str(version_b.version_id))
    assert wrong_version.status_code == 409
    correct = await preview(admin_client, documents)
    assert correct.status_code == 200, correct.text
    assert [i['source_ref']['characteristic_id'] for i in correct.json()['items']] == IDS
    assert all(i['source_ref']['fmea_id'] == str(source_a.fmea_id) for i in correct.json()['items'])
    assert all(i['source_ref']['accepted_source_version_id'] == str(version_a.version_id) for i in correct.json()['items'])
    assert 'Other factory private product' not in correct.text


@pytest.mark.asyncio
async def test_digest_binds_exact_approved_version_even_when_snapshot_and_candidate_keys_equal(db, admin_client, documents, admin_user):
    _, fmea, _ = documents
    before = (await preview(admin_client, documents)).json()
    fmea.graph_data = graph()
    another = await create_fmea_version(db, fmea, 'approve', '', admin_user.user_id)
    after = await preview(admin_client, documents, source_fmea_version_id=str(another.version_id))
    assert after.status_code == 200, after.text
    assert [i['candidate_key'] for i in before['items']] == [i['candidate_key'] for i in after.json()['items']]
    assert before['preview_digest'] != after.json()['preview_digest']
    assert (await apply(admin_client, documents, before, source_fmea_version_id=str(another.version_id))).status_code == 409
    assert await rows(db, documents[0].cp_id) == []


@pytest.mark.asyncio
async def test_cp_source_header_change_without_lock_bump_stales_digest(db, admin_client, documents):
    before = (await preview(admin_client, documents)).json()
    documents[0].fmea_ref_id = documents[1].fmea_id
    await db.flush()
    assert (await apply(admin_client, documents, before)).status_code == 409
    assert await rows(db, documents[0].cp_id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('change_type,major,minor', [('manual', 9, 0), (None, 9, 0), ('approve', 9, 1)])
async def test_current_approved_status_and_major_number_do_not_prove_source_approval(db, admin_client, documents, change_type, major, minor):
    cp, fmea, _ = documents
    fmea.status = 'approved'
    candidate = FMEAVersion(version_id=uuid.uuid4(), fmea_id=fmea.fmea_id, factory_id=cp.factory_id,
                            major_no=major, minor_no=minor, change_type=change_type, snapshot=graph(),
                            sha256_hash='trigger recomputes')
    db.add(candidate)
    await db.flush()
    response = await preview(admin_client, documents, source_fmea_version_id=str(candidate.version_id))
    assert response.status_code == 409, response.text
    assert await rows(db, cp.cp_id) == []


@pytest.mark.asyncio
async def test_duplicate_candidate_keys_are_not_repeated_insertions(db, admin_client, documents):
    result = (await preview(admin_client, documents)).json()
    key = result['items'][0]['candidate_key']
    response = await apply(admin_client, documents, result, selected_candidate_keys=[key, key])
    assert response.status_code == 409
    assert await rows(db, documents[0].cp_id) == []


@pytest.mark.asyncio
async def test_new_cp_create_response_eagerly_loads_empty_items(admin_client, admin_user):
    response = await admin_client.post("/api/control-plans", json={
        "title": "Task11 new target", "document_no": "CP-T11-" + uuid.uuid4().hex[:8],
        "product_line_code": "DC-DC-100",
    })
    assert response.status_code == 201, response.text
    assert response.json()["items"] == []
    assert response.json()["sync_pending"] is False
