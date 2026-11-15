"""Committed tenant scenarios with production authentication and honest transport.

Only initial users/scope/source documents are seeded. Candidate/confirmation/
correction helpers send requests and return the actual HTTP response, including
404 while their later-task routes do not exist. This is in-process API evidence,
not an independent application/process acceptance fixture.
"""
from contextlib import AsyncExitStack
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text, update, delete

from app.core.security import hash_password
from app.main import app
from app.models.agent_task import AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal
from app.models.capa_r6 import R6_TABLES
from app.models.factory import Factory, UserFactory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from tests.services.agent_runtime.conftest import committed_runtime  # noqa: F401

PASSWORD = 'R6SyntheticActorPassword123!'


class R6Actor:
    def __init__(self, case, *, user_id, role_id, username, client):
        self.case = case
        self.user_id, self.role_id, self.username = user_id, role_id, username
        self.client = client

    async def revoke(self, permission='capa'):
        """Commit authority changes in a session distinct from active requests."""
        async with self.case.session() as db:
            if permission in {'capa', 'fmea'}:
                await db.execute(update(RolePermission).where(
                    RolePermission.role_id == self.role_id, RolePermission.module == permission
                ).values(permission_level=0))
            elif permission == 'edit':
                await db.execute(update(RolePermission).where(
                    RolePermission.role_id == self.role_id, RolePermission.module == 'capa'
                ).values(permission_level=1))
            elif permission == 'source_b':
                await db.execute(delete(UserProductLine).where(
                    UserProductLine.user_id == self.user_id,
                    UserProductLine.product_line_code == self.case.source_b.product_line_code))
            elif permission == 'factory':
                await db.execute(delete(UserFactory).where(UserFactory.user_id == self.user_id))
            else:
                raise ValueError('Unknown fixture revocation')
            await db.commit()


class R6Case:
    def __init__(self, runtime):
        self.runtime = runtime
        self.binding, self.factory = runtime.binding, runtime.factory
        self.task_id, self.run_id = runtime.task_id, runtime.run_id
        self.actors = {}

    def session(self):
        return self.factory(binding=self.binding)

    def actor(self, mode='edit'):
        return self.actors[mode]

    async def report(self, report_id=None):
        async with self.session() as db:
            return await db.get(CAPAEightD, report_id or self.report_id)

    async def snapshot(self):
        """Fresh persisted facts for atomic rejection/no-side-effect assertions."""
        async with self.session() as db:
            body = await db.scalar(select(func.to_jsonb(CAPAEightD.__table__.table_valued())).where(
                CAPAEightD.report_id == self.report_id))
            counts = {}
            for table in (*R6_TABLES, 'capa_d5_measures', 'capa_d5_proposals',
                          'capa_d4_root_cause_revisions', 'capa_root_cause_verification', 'audit_logs'):
                counts[table] = await db.scalar(text(f'SELECT count(*) FROM {table}'))
            return dict(report=body, counts=counts)

    async def candidate(self, body, *, actor='edit', runtime_headers=None):
        """Transport for the future target-bound runtime candidate command."""
        return await self.actor(actor).client.post(
            '/api/agent/runtime/capa/d4/candidates', json=body, headers=runtime_headers)

    async def confirm(self, candidate_id, body, *, actor='edit'):
        return await self.actor(actor).client.post(
            f'/api/capa/{self.report_id}/d4-candidates/{candidate_id}/confirm', json=body)

    async def correct(self, measure_id, body, *, actor='edit'):
        return await self.actor(actor).client.post(
            f'/api/capa/{self.report_id}/d5-measures/{measure_id}/corrections', json=body)

    async def measure(self, proposal_id=None, *, final_text='R6 fixture adoption', actor='edit', operation_key=None):
        """Adopt an actual R5 pending proposal through its existing employee API.

        Caller creates the proposal through the normal R5 workflow. With no
        explicit ID, use an existing pending proposal; absence is an error,
        never a seeded or fabricated adoption.
        """
        if proposal_id is None:
            async with self.session() as db:
                proposal_id = await db.scalar(select(CapaD5Proposal.proposal_id).where(
                    CapaD5Proposal.report_id == self.report_id, CapaD5Proposal.state == 'pending'
                ).order_by(CapaD5Proposal.created_at.desc()))
            if proposal_id is None:
                raise LookupError('Create a real pending R5 proposal before adopting it')
        response = await self.actor(actor).client.post(
            f'/api/capa/{self.report_id}/d5-proposals/{proposal_id}/adopt',
            json=dict(operation_key=operation_key or uuid4().hex, final_text=final_text))
        response.raise_for_status()
        async with self.session() as db:
            result = await db.get(CapaD5Measure, UUID(response.json()['measure_id']))
            assert result is not None and result.final_text == final_text
            return result


@pytest_asyncio.fixture
async def r6_case(committed_runtime, monkeypatch):
    case = R6Case(committed_runtime)
    # Redirect only the real production session factory to this owned test DB;
    # authentication/scope dependencies and TenantSession guards remain intact.
    import app.database as database
    monkeypatch.setattr(database, 'tenant_async_session', case.factory)
    actor_rows = []
    async with case.session() as db:
        task = await db.get(AgentTask, case.task_id)
        case.report_id = task.target_capa_id
        report = await db.get(CAPAEightD, case.report_id)
        case.factory_id, case.line = report.factory_id, report.product_line_code
        line_b = ProductLine(code='R6B-' + uuid4().hex[:10], name='R6 extra source B', factory_id=case.factory_id)
        outside = Factory(code='R6X-' + uuid4().hex[:10], name='R6 outside factory', is_active=True)
        db.add_all([line_b, outside])
        await db.flush()
        case.outside_factory_id = outside.id
        outside_line = ProductLine(code='R6X-' + uuid4().hex[:10], name='R6 outside line', factory_id=outside.id)
        db.add(outside_line)
        await db.flush()
        docs = []
        for factory_id, line in [(case.factory_id, case.line), (case.factory_id, line_b.code),
                                 (outside.id, outside_line.code)]:
            doc = FMEADocument(document_no='R6-FMEA-' + uuid4().hex[:10], title='R6 controlled source',
                factory_id=factory_id, product_line_code=line,
                graph_data={'nodes': [{'id': 'cause', 'type': 'FailureCause', 'name': 'R6 source body'}], 'edges': []},
                created_by=committed_runtime.user_id)
            db.add(doc)
            docs.append(doc)
        await db.flush()
        case.source_a, case.source_b, case.outside_source = docs
        report.fmea_ref_id = case.source_a.fmea_id
        for mode in ('edit', 'view', 'second_edit', 'revocable'):
            role = RoleDefinition(role_key='r6-' + uuid4().hex[:12], name_zh='R6 fixture', name_en='R6 fixture',
                                  is_active=True, bypass_row_level_security=False)
            db.add(role)
            await db.flush()
            user = User(username='r6-' + uuid4().hex[:12], display_name='R6 ' + mode,
                password_hash=hash_password(PASSWORD), role_id=role.id, legacy_role='viewer',
                factory_id=case.factory_id, is_active=True)
            db.add(user)
            await db.flush()
            db.add_all([RolePermission(role_id=role.id, module='capa', permission_level=1 if mode == 'view' else 3),
                        RolePermission(role_id=role.id, module='fmea', permission_level=1),
                        UserFactory(user_id=user.user_id, factory_id=case.factory_id),
                        UserProductLine(user_id=user.user_id, product_line_code=case.line),
                        UserProductLine(user_id=user.user_id, product_line_code=line_b.code)])
            actor_rows.append((mode, user.user_id, role.id, user.username))
        await db.commit()
    async with case.runtime.engine.connect() as connection:
        case.slug = await connection.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'), {'id': case.binding.tenant_id})
    # Each fixture gets a distinct synthetic client IP, preserving the real
    # rate limiter without exhausting another fixture's per-IP budget.
    ip = '192.0.2.' + str(int(uuid4().hex[:2], 16))
    async with AsyncExitStack() as stack:
        for mode, user_id, role_id, username in actor_rows:
            client = await stack.enter_async_context(AsyncClient(
                transport=ASGITransport(app=app, client=(ip, 12345)), base_url='http://test',
                headers={'X-Tenant-ID': case.slug}))
            response = await client.post('/api/auth/login', json=dict(username=username, password=PASSWORD))
            assert response.status_code == 200, response.text
            client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
            case.actors[mode] = R6Actor(case, user_id=user_id, role_id=role_id, username=username, client=client)
        yield case
