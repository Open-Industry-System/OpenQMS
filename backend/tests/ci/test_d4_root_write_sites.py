"""Guard literal root-field writers; dynamic writers have behavioral tests."""
import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'app'


def literal_root_writes(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == 'd4_root_cause':
            found.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if ((isinstance(target, ast.Attribute) and target.attr == 'd4_root_cause')
                        or (isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
                            and target.slice.value == 'd4_root_cause')):
                    found.append(node)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == 'update' and node.args and isinstance(node.args[0], ast.Dict)
              and any(isinstance(key, ast.Constant) and key.value == 'd4_root_cause'
                      for key in node.args[0].keys)):
            found.append(node)
    return found


def root_write_sites(path, tree):
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    sites = Counter()
    for write in literal_root_writes(tree):
        owners = []
        ancestor = parents.get(write)
        while ancestor is not None:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owners.append(ancestor.name)
            ancestor = parents.get(ancestor)
        owner = '.'.join(reversed(owners)) or '<module>'
        # Shape and multiplicity detect additional writers even inside an
        # already-reviewed function; line numbers are intentionally irrelevant.
        shape = ast.dump(write, include_attributes=False)
        sites[(path, owner, shape)] += 1
    return sites


def test_literal_root_field_write_sites_are_reviewed():
    sites = Counter()
    for area in ('services', 'api'):
        for path in (ROOT / area).rglob('*.py'):
            tree = ast.parse(path.read_text())
            sites.update(root_write_sites(str(path.relative_to(ROOT)), tree))
    expected_write = ast.parse("CAPAEightD(d4_root_cause=finding.root_cause or '')").body[0].value.keywords[0]
    expected = Counter({('services/audit_service.py', 'create_capa_from_finding',
                        ast.dump(expected_write, include_attributes=False)): 1})
    assert sites == expected


def test_finding_creation_records_initial_revision():
    path = ROOT / 'services/audit_service.py'
    tree = ast.parse(path.read_text())
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'create_capa_from_finding')
    calls = [n for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == 'record_root_revision']
    assert len(calls) == 1
"""Offline admission ordering checks; database behavior is tested separately."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.derived_sources import SourceUnavailable


@pytest.mark.asyncio
async def test_fmea_permission_denied_before_document_query(monkeypatch):
    from app.services import fmea_agent_sources as source
    db = SimpleNamespace(execute=AsyncMock(), no_autoflush=nullcontext())
    monkeypatch.setattr(source, 'current_module_access', AsyncMock(side_effect=PermissionError()), raising=False)
    with pytest.raises(SourceUnavailable, match='^Source unavailable$'):
        await source.visible_fmea_source(db, SimpleNamespace(user=SimpleNamespace(user_id=uuid4())), uuid4())
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_fmea_visible_uses_scalar_query_after_permission(monkeypatch):
    from app.services import fmea_agent_sources as source
    identifier, factory = uuid4(), uuid4()
    row = SimpleNamespace(fmea_id=identifier, factory_id=factory, product_line_code='A')
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: row)), no_autoflush=nullcontext())
    access = AsyncMock(return_value=({}, SimpleNamespace(accessible_factory_ids=[factory]), SimpleNamespace(mode='EXPLICIT', codes=['A'])))
    monkeypatch.setattr(source, 'current_module_access', access, raising=False)
    scope = SimpleNamespace(user=SimpleNamespace(user_id=uuid4()))
    result = await source.visible_fmea_source(db, scope, identifier)
    access.assert_awaited_once_with(db, scope, Module.FMEA, PermissionLevel.VIEW)
    sql = str(db.execute.call_args.args[0])
    assert 'graph_data' not in sql and 'title' not in sql
    assert result.fmea_id == identifier

@pytest.mark.asyncio
async def test_node_second_read_enforces_uniqueness_and_size_again(monkeypatch):
    from app.services import fmea_agent_sources as source
    visible = source.VisibleFmeaSource(uuid4(), uuid4(), 'A', object())
    monkeypatch.setattr(source, 'visible_fmea_source', AsyncMock(return_value=visible))
    budget = SimpleNamespace(one=lambda: (1, 42))
    # The second SQL statement must return no row if a concurrent edit makes
    # the matching node oversized or non-unique after the preflight.
    read = SimpleNamespace(scalar_one_or_none=lambda: None, scalar_one=lambda: {'type': 'FailureCause', 'text': 'x' * 70000})
    db = SimpleNamespace(execute=AsyncMock(side_effect=[budget, read]), no_autoflush=nullcontext())
    with pytest.raises(SourceUnavailable):
        await source.failure_cause_version(db, visible, 'cause')
    second = str(db.execute.await_args_list[1].args[0]).lower()
    assert 'octet_length' in second and 'count(' in second

@pytest.mark.asyncio
@pytest.mark.parametrize(('old', 'expected'), [(None, 1), ('', 0)])
async def test_adopt_distinguishes_null_from_empty_root(monkeypatch, old, expected):
    from unittest.mock import Mock
    from app.schemas.capa_verification import AdoptRequest
    from app.services import capa_verification_service as service, capa_d4_provenance

    report = SimpleNamespace(report_id=uuid4(), factory_id=uuid4(), product_line_code='A', d4_root_cause=old)
    actor = SimpleNamespace(user_id=uuid4())
    db = SimpleNamespace(add=Mock(), commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(service, 'lock_current_material_write', AsyncMock(return_value=report))
    monkeypatch.setattr(service, '_find_existing_adoption', AsyncMock(return_value=None))
    monkeypatch.setattr(service, 'enqueue_embedding', AsyncMock())
    record = AsyncMock()
    monkeypatch.setattr(capa_d4_provenance, 'record_root_revision', record)
    await service.adopt_recommendation(db, report, AdoptRequest(d_step='d4', adopted_text='', source='rule'), actor)
    assert report.d4_root_cause == ''
    assert record.await_count == expected

@pytest.mark.asyncio
async def test_confirmed_change_appends_even_if_prior_digest_matches(monkeypatch):
    from unittest.mock import Mock
    from app.config import settings
    from app.services import capa_d4_provenance as provenance
    report, actor = uuid4(), uuid4()
    namespace = {'kind': 'single_public'}
    monkeypatch.setattr(provenance, 'current_field_namespace', AsyncMock(return_value=namespace))
    digest = provenance.field_hmac(settings.SECRET_KEY.encode(), namespace, report, 'A')
    latest = SimpleNamespace(field_hmac=digest, revision_no=1, revision_id=uuid4())
    db = SimpleNamespace(flush=AsyncMock(), execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: SimpleNamespace(d4_root_cause='A'))),
                         scalar=AsyncMock(return_value=latest), add=Mock())
    new = await provenance.record_root_revision(db, report_id=report, actor_id=actor, write_path='capa.update')
    assert new.revision_no == 2 and new.revision_id != latest.revision_id
    db.add.assert_called_once_with(new)


def test_write_site_scanner_detects_literal_dictionary_updates():
    tree = ast.parse("""\nvalues['d4_root_cause'] = 'A'\nvalues.update({'d4_root_cause': 'B'})\nother = {'d4_root_cause': 'read-only projection'}\n""")
    assert len(literal_root_writes(tree)) == 2


@pytest.mark.parametrize('extra_writer', [
    "\nasync def unreviewed_writer(db, report):\n    report.d4_root_cause = 'B'\n    await db.commit()\n",
    "\nasync def create_capa_from_finding(db, report):\n    other = CAPAEightD(d4_root_cause='B')\n    await db.commit()\n",
])
def test_same_file_extra_writer_is_rejected(tmp_path, monkeypatch, extra_writer):
    source = (ROOT / 'services/audit_service.py').read_text()
    (tmp_path / 'services').mkdir()
    (tmp_path / 'api').mkdir()
    (tmp_path / 'services/audit_service.py').write_text(source + extra_writer)
    monkeypatch.setitem(globals(), 'ROOT', tmp_path)
    with pytest.raises(AssertionError):
        test_literal_root_field_write_sites_are_reviewed()
