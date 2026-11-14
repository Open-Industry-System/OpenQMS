"""Authorization precedes existence, association diagnostics and bounded nodes."""
import hashlib
import hmac
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, select, update

from app.config import settings
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.agent.permissions.derived_sources import SourceUnavailable

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def source_case(db, default_factory):
    line_code = 'T3-' + uuid4().hex[:12]
    db.add(ProductLine(code=line_code, name='fixture', factory_id=default_factory.id))
    await db.flush()
    role = RoleDefinition(id=uuid4(), role_key='t3-' + uuid4().hex[:10], name_zh='fixture',
        name_en='fixture', is_active=True, bypass_row_level_security=False)
    db.add(role)
    await db.flush()
    actor = User(user_id=uuid4(), username='t3-' + uuid4().hex[:12], display_name='fixture',
        password_hash='fixture', legacy_role='viewer', role_id=role.id, factory_id=default_factory.id, is_active=True)
    db.add(actor)
    await db.flush()
    db.add_all([RolePermission(role_id=role.id, module='capa', permission_level=2),
        RolePermission(role_id=role.id, module='fmea', permission_level=1),
        UserProductLine(user_id=actor.user_id, product_line_code=line_code)])
    node = {'id': 'cause-1', 'type': 'FailureCause', 'data': {'label': 'fixture 原因'}}
    doc = FMEADocument(document_no='T3-' + uuid4().hex[:12], title='fixture',
        factory_id=default_factory.id, product_line_code=line_code, graph_data={'nodes': [node], 'edges': []})
    db.add(doc)
    await db.flush()
    return SimpleNamespace(actor=actor, scope=SimpleNamespace(user=actor), doc=doc, node=node)


class SQLSpy:
    def __init__(self, connection):
        self.connection = connection.sync_connection
        self.statements = []
    def record(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement.lower())
    def __enter__(self):
        event.listen(self.connection, 'before_cursor_execute', self.record)
        return self
    def __exit__(self, *args):
        event.remove(self.connection, 'before_cursor_execute', self.record)
    @property
    def node_reads(self):
        return [s for s in self.statements if 'graph_data' in s or 'jsonb_array_elements' in s]


@pytest.mark.asyncio
@pytest.mark.parametrize('node_id', ['cause-1', 'fictional'])
async def test_capa_edit_no_fmea_view_indistinguishable_zero_node_reads(db, source_case, node_id):
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    case = source_case
    await db.execute(update(RolePermission).where(RolePermission.role_id == case.actor.role_id,
        RolePermission.module == 'fmea').values(permission_level=0))
    with SQLSpy(await db.connection()) as spy:
        with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
            visible = await visible_fmea_source(db, case.scope, case.doc.fmea_id)
            await failure_cause_version(db, visible, node_id)
    assert spy.node_reads == []
    assert not any('from fmea_documents' in s for s in spy.statements)


@pytest.mark.asyncio
@pytest.mark.parametrize('hidden', ['factory', 'line', 'missing', 'inactive', 'no-lines'])
async def test_hidden_source_has_fixed_error_and_no_node_reads(db, source_case, hidden):
    from app.services.fmea_agent_sources import visible_fmea_source
    case = source_case
    fmea_id = case.doc.fmea_id
    if hidden == 'factory':
        other = Factory(code='T3-' + uuid4().hex[:10], name='fixture')
        db.add(other)
        await db.flush()
        case.doc.factory_id = other.id
    elif hidden == 'line':
        case.doc.product_line_code = 'HIDDEN-FIXTURE'
    elif hidden == 'missing':
        fmea_id = uuid4()
    elif hidden == 'inactive':
        case.actor.is_active = False
    else:
        from sqlalchemy import delete
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == case.actor.user_id))
    await db.flush()
    with SQLSpy(await db.connection()) as spy:
        with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
            await visible_fmea_source(db, case.scope, fmea_id)
    assert spy.node_reads == []


@pytest.mark.asyncio
async def test_visible_source_selects_only_coordinates_and_opaque_node_digest(db, source_case):
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version, FAILURE_CAUSE_REFERENCE
    case = source_case
    with SQLSpy(await db.connection()) as spy:
        visible = await visible_fmea_source(db, case.scope, case.doc.fmea_id)
        assert spy.node_reads == []
        digest = await failure_cause_version(db, visible, 'cause-1')
    expected = hmac.new(settings.SECRET_KEY.encode(), b'openqms.fmea.failure-cause-node.v1\n' +
        json.dumps(case.node, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
            allow_nan=False).encode(), hashlib.sha256).hexdigest()
    assert digest == expected and len(digest) == 64 and 'fixture' not in digest
    assert FAILURE_CAUSE_REFERENCE.source_projection_id == 'fmea.failure_cause.reference.v1'
    assert FAILURE_CAUSE_REFERENCE.owner.value == 'fmea'
    assert FAILURE_CAUSE_REFERENCE.minimum_level.value == 1
    assert len(spy.node_reads) == 2
    assert 'count(' in spy.node_reads[0] and 'octet_length' in spy.node_reads[0]
    assert 'jsonb_array_elements(case' in ' '.join(spy.node_reads).replace('\n', ' ')
    assert 'fmea_documents.title' not in ' '.join(spy.statements)


@pytest.mark.asyncio
@pytest.mark.parametrize('nodes', [[], [{'id': 'cause-1', 'type': 'FailureMode'}],
    [{'id': 'cause-1', 'type': 'FailureCause'}, {'id': 'cause-1', 'type': 'FailureCause'}],
    [{'id': 'cause-1', 'type': 'FailureCause', 'text': 'x' * (64 * 1024)}], None, {}, 'wrong'])
async def test_unknown_duplicate_wrong_type_or_over_budget_node_rejected(db, source_case, nodes):
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    case = source_case
    case.doc.graph_data = {'nodes': nodes, 'edges': []}
    await db.flush()
    visible = await visible_fmea_source(db, case.scope, case.doc.fmea_id)
    with SQLSpy(await db.connection()) as spy:
        with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
            await failure_cause_version(db, visible, 'cause-1')
    if nodes is None or not isinstance(nodes, list) or len(nodes) != 1 or 'text' in nodes[0]:
        assert len(spy.node_reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['permission', 'factory', 'line', 'inactive'])
async def test_source_visibility_is_fresh_before_node_read(db, source_case, change):
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    case = source_case
    visible = await visible_fmea_source(db, case.scope, case.doc.fmea_id)
    if change == 'permission':
        await db.execute(update(RolePermission).where(RolePermission.role_id == case.actor.role_id,
            RolePermission.module == 'fmea').values(permission_level=0))
    elif change == 'factory':
        case.actor.factory_id = None
    elif change == 'line':
        case.doc.product_line_code = 'CHANGED-FIXTURE'
    else:
        case.actor.is_active = False
    await db.flush()
    with SQLSpy(await db.connection()) as spy:
        with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
            await failure_cause_version(db, visible, 'cause-1')
    assert spy.node_reads == []


@pytest.mark.asyncio
async def test_diagnostic_result_rechecks_permission_after_node_read(db, source_case, monkeypatch):
    from app.services import fmea_agent_sources as sources
    case = source_case
    visible = await sources.visible_fmea_source(db, case.scope, case.doc.fmea_id)
    original = sources.visible_fmea_source
    calls = 0
    async def recheck(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            await db.execute(update(RolePermission).where(RolePermission.role_id == case.actor.role_id,
                RolePermission.module == 'fmea').values(permission_level=0))
        return await original(*args)
    monkeypatch.setattr(sources, 'visible_fmea_source', recheck)
    with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
        await sources.failure_cause_version(db, visible, 'cause-1')
    assert calls == 2


from tests.services.agent_runtime.conftest import committed_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['oversized', 'duplicate', 'revoke'])
async def test_external_commit_between_node_reads_is_rechecked(committed_runtime, monkeypatch, change):
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    case = committed_runtime
    async with case.factory(binding=case.binding) as db:
        line = await db.scalar(select(ProductLine))
        doc = FMEADocument(document_no='T3-RACE', title='fixture', factory_id=line.factory_id,
            product_line_code=line.code, graph_data={'nodes': [{'id': 'cause', 'type': 'FailureCause'}]})
        db.add(doc)
        await db.commit()
        fmea_id = doc.fmea_id
    async with case.factory(binding=case.binding) as db:
        visible = await visible_fmea_source(db, SimpleNamespace(user=SimpleNamespace(user_id=case.user_id)), fmea_id)
        execute = db.execute
        changed = False
        async def race(statement, *args, **kwargs):
            nonlocal changed
            result = await execute(statement, *args, **kwargs)
            if not changed and 'SELECT count(*), max(octet_length' in str(statement):
                changed = True
                async with case.factory(binding=case.binding) as writer:
                    if change == 'revoke':
                        await writer.execute(update(RolePermission).where(RolePermission.role_id == case.role_id,
                            RolePermission.module == 'fmea').values(permission_level=0))
                    else:
                        nodes = [{'id': 'cause', 'type': 'FailureCause'}]
                        if change == 'oversized':
                            nodes[0]['text'] = 'x' * 65536
                        else:
                            nodes = nodes * 2
                        await writer.execute(update(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
                            .values(graph_data={'nodes': nodes}))
                    await writer.commit()
            return result
        monkeypatch.setattr(db, 'execute', race)
        with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
            await failure_cause_version(db, visible, 'cause')
        assert changed


@pytest.mark.asyncio
async def test_finite_postgres_numeric_decoded_as_infinity_is_fixed_denial(db, source_case):
    from sqlalchemy import text
    from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
    case = source_case
    # PG numeric supports this finite value; the driver's JSON decoder yields
    # Python infinity, which must not escape as a raw serialization exception.
    graph = '{"nodes":[{"id":"cause-1","type":"FailureCause","number":' + '9' * 401 + '.1}]}'
    await db.execute(text('UPDATE fmea_documents SET graph_data=CAST(:graph AS jsonb) WHERE fmea_id=:id'),
        {'graph': graph, 'id': case.doc.fmea_id})
    visible = await visible_fmea_source(db, case.scope, case.doc.fmea_id)
    with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
        await failure_cause_version(db, visible, 'cause-1')
