"""Normal app subprocess for an explicitly registered, preserved R6 exercise.

Only initial synthetic identities, documents and report are provisioned here.
Business decisions, model calls and transitions belong to employee HTTP/UI.
The resource owner supplies the private directory; this is never a production
launcher and refuses an unverified container/database before importing the app.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets


def private_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    path.chmod(0o600)


async def bootstrap(directory):
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.core.tenant_transaction import TenantBinding
    from app.database import tenant_async_session, engine
    from app.models.capa import CAPAEightD
    from app.models.factory import UserFactory
    from app.models.fmea import FMEADocument
    from app.models.mes import MESConnection
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, RolePermission, UserProductLine
    from app.models.supplier import Supplier
    from app.models.user import User
    from app.schemas.platform import TenantCreateRequest
    from app.services.tenant_migrator import provision_new
    password = secrets.token_urlsafe(24)
    slug = 'r6-c9-' + secrets.token_hex(6)
    tenant = await provision_new(TenantCreateRequest(name='R6 C9 synthetic exercise', slug=slug,
        admin_email='c9-admin@example.test', admin_password=password))
    binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
    async with tenant_async_session(binding=binding) as db:
        admin = await db.scalar(select(User).where(User.email == 'c9-admin@example.test'))
        line = await db.scalar(select(ProductLine))
        actors = {}
        for name, level in [('qe', 3), ('colleague', 3), ('approver', 4), ('view', 1)]:
            role = RoleDefinition(role_key='c9-' + name, name_zh='C9 ' + name, name_en='C9 ' + name,
                is_active=True, bypass_row_level_security=False)
            db.add(role)
            await db.flush()
            user = User(username='c9-' + name, display_name='Synthetic C9 ' + name,
                password_hash=hash_password(password), role_id=role.id, legacy_role='viewer',
                factory_id=line.factory_id, is_active=True)
            db.add(user)
            await db.flush()
            db.add_all([RolePermission(role_id=role.id, module='capa', permission_level=level),
                RolePermission(role_id=role.id, module='fmea', permission_level=4),
                UserFactory(user_id=user.user_id, factory_id=line.factory_id),
                UserProductLine(user_id=user.user_id, product_line_code=line.code)])
            actors[name] = dict(user_id=str(user.user_id), role_id=str(role.id), username=user.username)
        supplier = Supplier(supplier_no='C9-SYN', name='C9 synthetic supplier', short_name='C9',
            factory_id=line.factory_id, created_by=admin.user_id)
        db.add(supplier)
        db.add(MESConnection(name='C9 IDs/status only', connector_type='mock', config={}, is_active=True,
            product_line_code=line.code, factory_id=line.factory_id, created_by=admin.user_id))
        await db.flush()
        source = FMEADocument(document_no='FMEA-C9-SYN', title='合成定位销既有控制',
            factory_id=line.factory_id, product_line_code=line.code, created_by=admin.user_id,
            graph_data={'nodes': [{'id': 'cause-a', 'type': 'FailureCause', 'data': {
                'label': '定位销磨损导致孔径超差',
                'description': '合成案例。现行控制已要求开班检查定位销并更换磨损件，记录检查人及结果。本次漏执行该既有检查；无需新增阈值、频次或文件义务。'}}], 'edges': []})
        db.add(source)
        await db.flush()
        report = CAPAEightD(document_no='8D-C9-SYN', title='合成：定位销点检漏执行',
            status='D4_ROOT_CAUSE', d2_description='合成批次C9：200件中12件孔径超差，发现定位销磨损。无真实客户或生产资料。',
            d3_interim='隔离该合成批次200件并逐件复测；暂停该夹具使用。',
            factory_id=line.factory_id, product_line_code=line.code, created_by=admin.user_id,
            fmea_ref_id=source.fmea_id, supplier_id=supplier.supplier_id)
        db.add(report)
        await db.commit()
        private_json(directory / 'session.json', dict(tenant=slug, tenant_id=str(tenant.id),
            schema=tenant.schema_name, generation=tenant.generation, factory_id=str(line.factory_id),
            line=line.code, report_id=str(report.report_id), fmea_id=str(source.fmea_id),
            admin=admin.username, password=password, actors=actors))
    await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('--port', type=int)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    from tests.ci.python_isolation import disable_implicit_dotenv
    disable_implicit_dotenv()
    from tests.ci.owned_resources import verify_owned_instance, verify_owned_database
    verify_owned_database(verify_owned_instance(os.environ))
    if args.bootstrap:
        if (args.directory / 'session.json').exists():
            raise ValueError('preserved exercise already exists')
        asyncio.run(bootstrap(args.directory))
        return
    if args.live:
        # Approval to reuse this exact owner-only credential was obtained by
        # the controller. It stays in this backend process, never child/Node.
        from dotenv import dotenv_values
        key = dotenv_values('/Users/sam/Documents/Code/OpenQMS/.env.r5.local', interpolate=False).get(
            'R5_MODEL_CREDENTIAL_OPENAI_TRIAL')
        if not key:
            raise ValueError('approved R5 credential unavailable')
        os.environ['R5_MODEL_CREDENTIAL_OPENAI_TRIAL'] = key
    if not args.port:
        raise ValueError('explicit loopback app port required')
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=args.port,
        access_log=False, log_level='critical', proxy_headers=False)


if __name__ == '__main__':
    main()
