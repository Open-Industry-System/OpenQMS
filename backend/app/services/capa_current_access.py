"""Fresh CAPA read authority shared by employee previews and runtime tasks."""
from types import SimpleNamespace

from sqlalchemy import select, text

from app.config import settings
from app.core.factory_scope import resolve_factory_scope, resolve_product_line_scope
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding, TenantUnavailable
from app.database import TenantSession
from app.models.capa import CAPAEightD
from app.models.factory import UserFactory
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User


async def require_business_namespace(db):
    binding = db.info.get('tenant_binding')
    if settings.TENANT_MODE == 'single':
        if binding is not None or isinstance(db.sync_session, TenantSession):
            raise PermissionError('Business namespace unavailable')
        with db.no_autoflush:
            await db.execute(text('SET LOCAL search_path TO public, pg_catalog'))
        return
    if (not isinstance(db.sync_session, TenantSession) or not isinstance(binding, TenantBinding)
            or binding.mode != 'business'):
        raise PermissionError('Business namespace unavailable')
    try:
        with db.no_autoflush:
            row = (await db.execute(text('SELECT status,schema_name,generation FROM public.tenants WHERE id=:id'),
                {'id': binding.tenant_id})).one_or_none()
    except TenantUnavailable:
        raise PermissionError('Business namespace unavailable') from None
    if (row is None or row.status != 'active' or row.schema_name != binding.schema_name or row.generation != binding.generation):
        raise PermissionError('Business namespace unavailable')


async def current_capa_access(db, scope):
    await require_business_namespace(db)
    with db.no_autoflush:
        identity = (await db.execute(select(User.factory_id, User.role_id, RoleDefinition.bypass_row_level_security)
            .join(RoleDefinition, User.role_id == RoleDefinition.id).where(User.user_id == scope.user.user_id,
                User.is_active.is_(True), RoleDefinition.is_active.is_(True)))).one_or_none()
        if identity is None: raise PermissionError('Current CAPA VIEW required')
        levels = dict((await db.execute(select(RolePermission.module, RolePermission.permission_level)
            .where(RolePermission.role_id == identity.role_id))).all())
        if levels.get(Module.CAPA, PermissionLevel.NONE) < PermissionLevel.VIEW:
            raise PermissionError('Current CAPA VIEW required')
        factory_ids = list((await db.scalars(select(UserFactory.factory_id).where(UserFactory.user_id == scope.user.user_id))).all())
        line_codes = list((await db.scalars(select(UserProductLine.product_line_code).where(UserProductLine.user_id == scope.user.user_id))).all())
    user = SimpleNamespace(factory_id=identity.factory_id,
        role_definition=SimpleNamespace(bypass_row_level_security=identity.bypass_row_level_security))
    factories = resolve_factory_scope(user, factory_ids, levels.get(Module.GROUP, PermissionLevel.NONE) >= PermissionLevel.ADMIN)
    lines = resolve_product_line_scope(user, line_codes, factories)
    return levels, factories, lines


def capa_target_filters(query, factories, lines):
    if factories.accessible_factory_ids is not None:
        query = query.where(CAPAEightD.factory_id.in_(factories.accessible_factory_ids))
    if lines.mode != 'ALL': query = query.where(CAPAEightD.product_line_code.in_(lines.codes or []))
    return query


async def current_capa_target(db, report_id, factories, lines):
    with db.no_autoflush:
        target = await db.scalar(capa_target_filters(select(CAPAEightD).where(CAPAEightD.report_id == report_id),
            factories, lines).execution_options(populate_existing=True))
    if target is None: raise LookupError('8D report not found')
    return target


async def current_capa_actor_access(db, actor_id, required_level: PermissionLevel):
    """Resolve the server-side actor's live CAPA role and scope."""
    levels, factories, lines = await current_capa_access(
        db, SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    )
    if levels.get(Module.CAPA, PermissionLevel.NONE) < required_level:
        raise PermissionError('Current CAPA permission required')
    return factories, lines


async def current_capa_actor_product_line(
    db, actor_id, factory_id, product_line_code, required_level: PermissionLevel,
) -> None:
    """Require a live CAPA scope that includes a destination product line."""
    factories, lines = await current_capa_actor_access(db, actor_id, required_level)
    if factories.accessible_factory_ids is not None and factory_id not in factories.accessible_factory_ids:
        raise PermissionError('Current CAPA permission required')
    if lines.mode != 'ALL' and product_line_code not in (lines.codes or []):
        raise PermissionError('Current CAPA permission required')


async def current_capa_actor_target(db, actor_id, report_id, required_level: PermissionLevel) -> CAPAEightD:
    """Resolve fresh CAPA access from the server-side actor identity only."""
    levels, factories, lines = await current_capa_access(
        db, SimpleNamespace(user=SimpleNamespace(user_id=actor_id))
    )
    if levels.get(Module.CAPA, PermissionLevel.NONE) < required_level:
        raise PermissionError('Current CAPA permission required')
    return await current_capa_target(db, report_id, factories, lines)
