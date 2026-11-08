"""Real-commit and independent-connection Task 5 boundaries, in qms_test only."""
import asyncio
import os
import re
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from tests.embedding_isolation import require_isolated_test_database
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.tenant_utils import current_tenant_schema
from app.models.control_plan import ControlPlan
from app.models.control_plan_version import ControlPlanVersion
from app.models.factory import Factory, UserFactory
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.schemas.control_plan import ImportFromFMEARequest
from app.services import control_plan_service as service
from app.services.version_service import compute_pg_jsonb_hash
from tests.test_cp_characteristic_import import IDS, graph, rows


@pytest_asyncio.fixture
async def isolated_tenants():
    """Clone actual columns/indexes/FKs/triggers, never alter public tables.

    Disposable schemas allow real commits without disabling shared immutability
    triggers for cleanup. No new database/container or dependency is needed.
    """
    url = require_isolated_test_database(os.environ)
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=True)
    tables = ('factories', 'product_lines', 'role_definitions', 'users', 'role_permissions',
              'user_factories', 'user_product_lines', 'fmea_documents', 'fmea_versions',
              'control_plans', 'control_plan_items', 'control_plan_versions', 'audit_logs')
    schemas = ['tenant_import_' + uuid.uuid4().hex[:16] for _ in range(2)]
    async with engine.begin() as conn:
        for schema in schemas:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            for table in tables:
                await conn.execute(text(f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)'))
            for table in tables:
                definitions = (await conn.execute(text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid=to_regclass(:table) AND contype='f'"
                ), {'table': 'public.' + table})).all()
                for name, definition in definitions:
                    definition = re.sub(r'REFERENCES (?:public\.)?([a-z_]+)',
                                        lambda m: f'REFERENCES "{schema if m[1] in tables else "public"}"."{m[1]}"', definition)
                    await conn.execute(text(f'ALTER TABLE "{schema}"."{table}" ADD CONSTRAINT "{name}" {definition}'))
                triggers = (await conn.execute(text(
                    "SELECT pg_get_triggerdef(oid) FROM pg_trigger "
                    "WHERE tgrelid=to_regclass(:table) AND NOT tgisinternal"
                ), {'table': 'public.' + table})).scalars().all()
                for definition in triggers:
                    definition = definition.replace(f' ON public.{table} ', f' ON "{schema}"."{table}" ')
                    await conn.execute(text(definition))
    try:
        yield sessions, schemas
    finally:
        async with engine.begin() as conn:
            for schema in schemas:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def seed_tenant(sessions, schema, *, identical_ids=None):
    ids = identical_ids or [uuid.uuid4() for _ in range(7)]
    factory_id, other_factory_id, role_id, user_id, cp_id, fmea_id, version_id = ids
    async with sessions() as db:
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        db.add_all([Factory(id=factory_id, code='FIRST', name='Same name'),
                    Factory(id=other_factory_id, code='SECOND', name='Same name'),
                    RoleDefinition(id=role_id, role_key='importer', name_zh='导入', name_en='Importer', bypass_row_level_security=True)])
        await db.flush()
        db.add(User(user_id=user_id, username='importer', password_hash='not-used', role_id=role_id,
                    legacy_role='viewer', factory_id=factory_id, is_active=True))
        db.add(ProductLine(code='LINE', name='Same name', factory_id=factory_id))
        db.add_all([RolePermission(role_id=role_id, module='planning', permission_level=2),
                    RolePermission(role_id=role_id, module='fmea', permission_level=1)])
        await db.flush()
        db.add(ControlPlan(cp_id=cp_id, document_no='CP-SAME', title='Same name', factory_id=factory_id,
                           product_line_code='LINE', status='draft', created_by=user_id))
        db.add(FMEADocument(fmea_id=fmea_id, document_no='PFMEA-SAME', title='Same name', factory_id=factory_id,
                            product_line_code='LINE', fmea_type='PFMEA', status='rework', graph_data={'nodes': [], 'edges': []}))
        await db.flush()
        db.add(FMEAVersion(version_id=version_id, fmea_id=fmea_id, factory_id=factory_id,
                           major_no=1, minor_no=0, change_type='approve', snapshot=graph(),
                           sha256_hash=await compute_pg_jsonb_hash(db, graph()), created_by=user_id))
        await db.commit()
    body = {'fmea_id': str(fmea_id), 'source_fmea_version_id': str(version_id),
            'expected_lock_version': 0, 'step_ids': ['s1']}
    return ids, body


async def tenant_scope(db, schema, user_id):
    await db.execute(text(f'SET search_path TO "{schema}", public'))
    user = await db.get(User, user_id)
    return RequestScope(FactoryScope([user.factory_id], user.factory_id), user.factory_id, ProductLineScope('ALL', None), user)


async def import_request(db, ids, body, scope):
    req = ImportFromFMEARequest(**body)
    result = await service.preview_import_from_fmea(db, ids[4], req, scope)
    req.preview_digest = result['preview_digest']
    req.selected_candidate_keys = [i['candidate_key'] for i in result['items']]
    return req


@pytest.mark.asyncio
async def test_real_commit_materializes_response_before_expiration_and_no_business_read_after_commit(isolated_tenants):
    sessions, schemas = isolated_tenants
    ids, body = await seed_tenant(sessions, schemas[0])
    token = current_tenant_schema.set(schemas[0])
    try:
        async with sessions() as db:
            scope = await tenant_scope(db, schemas[0], ids[3])
            req = await import_request(db, ids, body, scope)
            commits = []
            def committed(session):
                if not session.in_nested_transaction():
                    commits.append(True)
            event.listen(db.sync_session, 'after_commit', committed)
            returned = await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
            assert len(commits) == 1
            assert not db.in_transaction(), 'post-commit refresh/read reopened a business transaction'
            assert [str(i.source_characteristic_ref.characteristic_id) for i in returned] == IDS
            assert all(i.source_characteristic_ref.accepted_source_version_id == ids[6] for i in returned)
        async with sessions() as verify:
            await verify.execute(text(f'SET search_path TO "{schemas[0]}", public'))
            assert len(await rows(verify, ids[4])) == 5
            cp = await verify.get(ControlPlan, ids[4])
            assert cp.lock_version == 1 and cp.source_fmea_version_id == ids[6]
            version = await verify.scalar(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == ids[4]))
            assert version.source_fmea_version_id == ids[6] and len(version.items_snapshot) == 5
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_two_tenants_same_ids_cannot_replay_digest_or_read_other_source(isolated_tenants):
    sessions, schemas = isolated_tenants
    ids, body = await seed_tenant(sessions, schemas[0])
    await seed_tenant(sessions, schemas[1], identical_ids=ids)
    previews = []
    for schema in schemas:
        token = current_tenant_schema.set(schema)
        try:
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                previews.append(await service.preview_import_from_fmea(db, ids[4], ImportFromFMEARequest(**body), scope))
        finally:
            current_tenant_schema.reset(token)
    assert previews[0]['preview_digest'] != previews[1]['preview_digest']
    token = current_tenant_schema.set(schemas[1])
    try:
        async with sessions() as db:
            scope = await tenant_scope(db, schemas[1], ids[3])
            req = ImportFromFMEARequest(**body, preview_digest=previews[0]['preview_digest'],
                                        selected_candidate_keys=[i['candidate_key'] for i in previews[0]['items']])
            with pytest.raises(service.CharacteristicImportError, match='预览已过期'):
                await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
            assert await rows(db, ids[4]) == []
            async with sessions() as other:
                await other.execute(text(f'SET search_path TO "{schemas[0]}", public'))
                private_id = uuid.uuid4()
                other.add(FMEADocument(fmea_id=private_id, document_no='PRIVATE', title='Tenant A private',
                                       factory_id=ids[0], product_line_code='LINE'))
                await other.commit()
            req.fmea_id = private_id
            with pytest.raises(service.CharacteristicImportError) as exc:
                await service.preview_import_from_fmea(db, ids[4], req, scope)
            assert exc.value.status_code == 404 and 'Tenant A private' not in str(exc.value)
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize('authority_change', ['first_factory_grant', 'permission_revoke', 'line_revoke', 'role_deactivate'])
async def test_authority_mutations_cannot_race_authorized_import(isolated_tenants, monkeypatch, authority_change):
    """Separate connection must block on authority rows until sole commit."""
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    if authority_change == 'line_revoke':
        async with sessions() as seed:
            await seed.execute(text(f'SET search_path TO "{schema}", public'))
            role = await seed.get(RoleDefinition, ids[2])
            role.bypass_row_level_security = False
            seed.add(UserProductLine(user_id=ids[3], product_line_code='LINE'))
            await seed.commit()
    checked = asyncio.Event()
    release = asyncio.Event()
    original = service._import_authority
    async def pause_authority(*args, **kwargs):
        result = await original(*args, **kwargs)
        if kwargs.get('lock'):
            checked.set()
            await release.wait()
        return result
    monkeypatch.setattr(service, '_import_authority', pause_authority)
    async def importing():
        token = current_tenant_schema.set(schema)
        try:
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                req = await import_request(db, ids, body, scope)
                return await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
        finally:
            current_tenant_schema.reset(token)
    task = asyncio.create_task(importing())
    try:
        await asyncio.wait_for(checked.wait(), 5)
        async with sessions() as revoker:
            await revoker.execute(text(f'SET search_path TO "{schema}", public'))
            await revoker.execute(text("SET LOCAL lock_timeout = '150ms'"))
            with pytest.raises(Exception, match='lock timeout'):
                if authority_change == 'first_factory_grant':
                    # Absent assignment -> insertion replaces fallback-own scope.
                    revoker.add(UserFactory(user_id=ids[3], factory_id=ids[1]))
                    await revoker.flush()
                elif authority_change == 'permission_revoke':
                    await revoker.execute(text("UPDATE role_permissions SET permission_level=0 WHERE role_id=:rid AND module='fmea'"), {'rid': ids[2]})
                elif authority_change == 'line_revoke':
                    await revoker.execute(text('DELETE FROM user_product_lines WHERE user_id=:uid'), {'uid': ids[3]})
                else:
                    await revoker.execute(text('UPDATE role_definitions SET is_active=false WHERE id=:rid'), {'rid': ids[2]})
            await revoker.rollback()
        release.set()
        assert len(await asyncio.wait_for(task, 5)) == 5
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_real_stage_failure_persists_nothing_in_separate_session(isolated_tenants, monkeypatch):
    from app.models.audit import AuditLog
    from sqlalchemy import func
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    original = service.stage_cp_version
    async def fail_after_snapshot(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError('after version flush')
    monkeypatch.setattr(service, 'stage_cp_version', fail_after_snapshot)
    token = current_tenant_schema.set(schema)
    try:
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            req = await import_request(db, ids, body, scope)
            with pytest.raises(RuntimeError, match='after version flush'):
                await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
            await db.commit()
        async with sessions() as verify:
            await verify.execute(text(f'SET search_path TO "{schema}", public'))
            assert await rows(verify, ids[4]) == []
            cp = await verify.get(ControlPlan, ids[4])
            assert cp.lock_version == 0 and cp.fmea_ref_id is None and cp.source_fmea_version_id is None
            assert await verify.scalar(select(func.count()).select_from(ControlPlanVersion)) == 0
            assert await verify.scalar(select(func.count()).select_from(AuditLog)) == 0
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_missing_tenant_table_cannot_resolve_from_public(isolated_tenants):
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    async with sessions() as setup:
        await setup.execute(text(f'DROP TABLE "{schema}".control_plan_versions CASCADE'))
        await setup.commit()
    token = current_tenant_schema.set(schema)
    try:
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            with pytest.raises(service.CharacteristicImportError) as exc:
                await service.preview_import_from_fmea(db, ids[4], ImportFromFMEARequest(**body), scope)
            assert exc.value.status_code == 404
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_revoker_commits_first_waiting_apply_rechecks_permission(isolated_tenants):
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        async with sessions() as reader:
            scope = await tenant_scope(reader, schema, ids[3])
            req = await import_request(reader, ids, body, scope)
        async with sessions() as revoker:
            await revoker.execute(text(f'SET search_path TO "{schema}", public'))
            await revoker.execute(text("UPDATE role_permissions SET permission_level=0 WHERE role_id=:rid AND module='fmea'"), {'rid': ids[2]})
            async def applying():
                async with sessions() as db:
                    scope = await tenant_scope(db, schema, ids[3])
                    return await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
            task = asyncio.create_task(applying())
            try:
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(task), .15)
                await revoker.commit()
                with pytest.raises(service.CharacteristicImportError) as exc:
                    await asyncio.wait_for(task, 5)
                assert exc.value.status_code == 403
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        async with sessions() as verify:
            await verify.execute(text(f'SET search_path TO "{schema}", public'))
            assert await rows(verify, ids[4]) == []
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_concurrent_same_preview_only_one_apply_commits_then_fresh_repeat_no_add(isolated_tenants, monkeypatch):
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    token = current_tenant_schema.set(schema)
    ready, release = asyncio.Event(), asyncio.Event()
    original = service.stage_cp_version
    async def paused_stage(*args, **kwargs):
        result = await original(*args, **kwargs)
        ready.set()
        await release.wait()
        return result
    monkeypatch.setattr(service, 'stage_cp_version', paused_stage)
    tasks = []
    try:
        async with sessions() as reader:
            scope = await tenant_scope(reader, schema, ids[3])
            req = await import_request(reader, ids, body, scope)
        async def applying(request):
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                return await service.import_from_fmea(db, ids[4], request, ids[3], scope=scope)
        first = asyncio.create_task(applying(req))
        tasks.append(first)
        await asyncio.wait_for(ready.wait(), 5)
        second = asyncio.create_task(applying(req))
        tasks.append(second)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), .15)
        release.set()
        accepted = await asyncio.wait_for(first, 5)
        with pytest.raises(service.CharacteristicImportError) as exc:
            await asyncio.wait_for(second, 5)
        assert exc.value.status_code == 409
        async with sessions() as db:
            scope = await tenant_scope(db, schema, ids[3])
            again = await import_request(db, ids, {**body, 'expected_lock_version': 1}, scope)
            returned = await service.import_from_fmea(db, ids[4], again, ids[3], scope=scope)
            assert [i.item_id for i in returned] == [i.item_id for i in accepted]
        async with sessions() as verify:
            await verify.execute(text(f'SET search_path TO "{schema}", public'))
            assert len(await rows(verify, ids[4])) == 5
            assert len((await verify.scalars(select(ControlPlanVersion))).all()) == 1
            cp = await verify.get(ControlPlan, ids[4])
            assert cp.lock_version == 1
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_preview_runs_in_real_read_only_transaction(isolated_tenants):
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    token = current_tenant_schema.set(schema)
    try:
        async with sessions() as db:
            await db.execute(text('SET TRANSACTION READ ONLY'))
            scope = await tenant_scope(db, schema, ids[3])
            result = await service.preview_import_from_fmea(db, ids[4], ImportFromFMEARequest(**body), scope)
            assert len(result['items']) == 5
            assert await rows(db, ids[4]) == []
            assert (await db.get(ControlPlan, ids[4])).lock_version == 0
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_actual_permission_replacement_wins_then_import_reads_revocation_without_deadlock(isolated_tenants, monkeypatch):
    from app.services.permission_service import update_role_permissions, get_role_permissions
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    token = current_tenant_schema.set(schema)
    deleted, resume, import_role_locked = asyncio.Event(), asyncio.Event(), asyncio.Event()
    tasks = []
    try:
        async with sessions() as reader:
            scope = await tenant_scope(reader, schema, ids[3])
            req = await import_request(reader, ids, body, scope)
        async def replacing():
            async with sessions() as db:
                await db.execute(text(f'SET search_path TO "{schema}", public'))
                execute = db.execute
                async def after_delete(statement, *args, **kwargs):
                    result = await execute(statement, *args, **kwargs)
                    if str(statement).startswith('DELETE FROM role_permissions'):
                        deleted.set()
                        await resume.wait()
                    return result
                monkeypatch.setattr(db, 'execute', after_delete)
                await update_role_permissions(db, 'importer', [
                    {'module': 'planning', 'level': 2}, {'module': 'fmea', 'level': 0},
                ])
                await db.commit()
        async def importing():
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                execute = db.execute
                async def after_role_lock(statement, *args, **kwargs):
                    result = await execute(statement, *args, **kwargs)
                    sql = str(statement)
                    if 'FROM role_definitions' in sql and 'FOR UPDATE' in sql:
                        import_role_locked.set()
                    return result
                monkeypatch.setattr(db, 'execute', after_role_lock)
                return await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
        replacement = asyncio.create_task(replacing())
        tasks.append(replacement)
        await asyncio.wait_for(deleted.wait(), 5)
        importing_task = asyncio.create_task(importing())
        tasks.append(importing_task)
        # Old ordering lets import lock role after admin DELETE; replacement FK
        # insertion then completes the real deadlock cycle. Fixed ordering keeps
        # import waiting on the role already owned by the replacement writer.
        try:
            await asyncio.wait_for(import_role_locked.wait(), .15)
        except asyncio.TimeoutError:
            pass
        resume.set()
        replaced, imported = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 8)
        assert replaced is None, f'permission replacement failed: {replaced!r}'
        assert isinstance(imported, service.CharacteristicImportError), repr(imported)
        assert imported.status_code == 403
        async with sessions() as verify:
            await verify.execute(text(f'SET search_path TO "{schema}", public'))
            assert await get_role_permissions(verify, ids[2]) == {'planning': 2, 'fmea': 0}
            assert await rows(verify, ids[4]) == []
            cp = await verify.get(ControlPlan, ids[4])
            assert cp.lock_version == 0 and cp.fmea_ref_id is None
            assert (await verify.scalars(select(ControlPlanVersion))).all() == []
    finally:
        resume.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_import_wins_actual_permission_replacement_waits_then_future_access_denied(isolated_tenants, monkeypatch):
    from app.services.permission_service import update_role_permissions, get_role_permissions
    sessions, schemas = isolated_tenants
    schema = schemas[0]
    ids, body = await seed_tenant(sessions, schema)
    token = current_tenant_schema.set(schema)
    staged, resume = asyncio.Event(), asyncio.Event()
    tasks = []
    original = service.stage_cp_version
    async def paused_stage(*args, **kwargs):
        result = await original(*args, **kwargs)
        staged.set()
        await resume.wait()
        return result
    monkeypatch.setattr(service, 'stage_cp_version', paused_stage)
    try:
        async def importing():
            async with sessions() as db:
                scope = await tenant_scope(db, schema, ids[3])
                req = await import_request(db, ids, body, scope)
                return await service.import_from_fmea(db, ids[4], req, ids[3], scope=scope)
        async def replacing():
            async with sessions() as db:
                await db.execute(text(f'SET search_path TO "{schema}", public'))
                await update_role_permissions(db, 'importer', [
                    {'module': 'planning', 'level': 2}, {'module': 'fmea', 'level': 0},
                ])
                await db.commit()
        first = asyncio.create_task(importing())
        tasks.append(first)
        await asyncio.wait_for(staged.wait(), 5)
        second = asyncio.create_task(replacing())
        tasks.append(second)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), .15)
        resume.set()
        returned, replaced = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert len(returned) == 5 and replaced is None
        async with sessions() as verify:
            scope = await tenant_scope(verify, schema, ids[3])
            assert await get_role_permissions(verify, ids[2]) == {'planning': 2, 'fmea': 0}
            assert len(await rows(verify, ids[4])) == 5
            with pytest.raises(service.CharacteristicImportError) as exc:
                await service.preview_import_from_fmea(verify, ids[4], ImportFromFMEARequest(**{**body, 'expected_lock_version': 1}), scope)
            assert exc.value.status_code == 403
    finally:
        resume.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_permission_replacement_fresh_reads_editability_before_deleting(db):
    from app.services.permission_service import update_role_permissions, get_role_permissions
    role = RoleDefinition(id=uuid.uuid4(), role_key=uuid.uuid4().hex[:20], name_zh='测试', name_en='Test', is_editable=True)
    db.add(role)
    await db.flush()
    db.add(RolePermission(role_id=role.id, module='planning', permission_level=2))
    await db.flush()
    # Keep a stale editable object in this session's identity map.
    await db.execute(text('UPDATE role_definitions SET is_editable=false WHERE id=:rid'), {'rid': role.id})
    assert role.is_editable is True
    with pytest.raises(ValueError, match='权限不可修改'):
        await update_role_permissions(db, role.role_key, [{'module': 'planning', 'level': 0}])
    assert await get_role_permissions(db, role.id) == {'planning': 2}


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['valid', 'missing_role', 'not_editable', 'invalid_module'])
async def test_permission_replacement_keeps_validation_and_caller_commit(db, monkeypatch, case):
    from app.services.permission_service import update_role_permissions, get_role_permissions
    role = RoleDefinition(id=uuid.uuid4(), role_key=uuid.uuid4().hex[:20], name_zh='测试', name_en='Test', is_editable=case != 'not_editable')
    db.add(role)
    await db.flush()
    db.add(RolePermission(role_id=role.id, module='planning', permission_level=2))
    await db.flush()
    async def forbidden_commit():
        raise AssertionError('permission service must retain caller commit ownership')
    monkeypatch.setattr(db, 'commit', forbidden_commit)
    role_key = 'missing-' + uuid.uuid4().hex[:8] if case == 'missing_role' else role.role_key
    requested = [{'module': 'not-a-module' if case == 'invalid_module' else 'fmea', 'level': 1}]
    if case == 'valid':
        await update_role_permissions(db, role_key, requested)
        await db.flush()
        assert await get_role_permissions(db, role.id) == {'fmea': 1}
    else:
        expected = {'missing_role': '不存在', 'not_editable': '权限不可修改', 'invalid_module': '无效模块'}[case]
        with pytest.raises(ValueError, match=expected):
            await update_role_permissions(db, role_key, requested)
        assert await get_role_permissions(db, role.id) == {'planning': 2}
