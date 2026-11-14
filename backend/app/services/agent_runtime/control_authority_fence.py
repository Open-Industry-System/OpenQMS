"""NOWAIT authority fences for typed recovery control transactions.

Locks do not authorize: callers must rerun the normal live checks after them.
"""
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.models.agent_d4_recovery import D4TaskParentGrant
from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
from app.models.agent_plugin import AgentPluginGrant
from app.models.agent_task import AgentTaskGrant
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
from app.models.factory import UserFactory
from app.models.fmea import FMEADocument
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User


class ControlFenceBusy(Exception):
    """A conflicting writer won the control authorization race."""


async def _no_wait(db, statement):
    try:
        return await db.execute(statement.with_for_update(nowait=True))
    except DBAPIError as exc:
        if getattr(exc.orig, 'sqlstate', None) != '55P03':
            raise
        await db.rollback()
        raise ControlFenceBusy() from None


async def lock_control_target(db, task):
    """Lock only target coordinates; never load root text or source graph."""
    result = await _no_wait(db, select(CAPAEightD.report_id).where(
        CAPAEightD.report_id == task.target_capa_id, CAPAEightD.factory_id == task.factory_id))
    row = result.one_or_none()
    if row is None:
        raise PermissionError('Recovery unavailable')
    return row.report_id


async def lock_employee_acl(db, user_ids, *, control_only=False):
    """Lock all users first, then distinct roles and their associated ACL rows."""
    users = sorted(set(user_ids), key=str)
    roles = set()
    with db.no_autoflush:
        for user_id in users:
            row = (await _no_wait(db, select(User.user_id, User.role_id).where(
                User.user_id == user_id))).one_or_none()
            if row is None or row.role_id is None:
                raise PermissionError('Recovery unavailable')
            roles.add(row.role_id)
        for role_id in sorted(roles, key=str):
            role = (await _no_wait(db, select(RoleDefinition.id).where(
                RoleDefinition.id == role_id))).scalar_one_or_none()
            if role is None:
                raise PermissionError('Recovery unavailable')
        permissions = select(RolePermission.id).where(RolePermission.role_id.in_(roles))
        if control_only:
            permissions = permissions.where(RolePermission.module.in_(['capa', 'group']))
        await _no_wait(db, permissions.order_by(RolePermission.role_id, RolePermission.id))
        await _no_wait(db, select(UserFactory.id).where(UserFactory.user_id.in_(users))
            .order_by(UserFactory.user_id, UserFactory.id))
        await _no_wait(db, select(UserProductLine.id).where(UserProductLine.user_id.in_(users))
            .order_by(UserProductLine.user_id, UserProductLine.id))


async def require_restart_target_source(db, task, authorized_source):
    """Compare the locked target to the already authorized source before touching FMEA."""
    if authorized_source is None or authorized_source.target_report_id != task.target_capa_id:
        raise PermissionError('Recovery unavailable')
    with db.no_autoflush:
        fmea_id = await db.scalar(select(CAPAEightD.fmea_ref_id).where(
            CAPAEightD.report_id == task.target_capa_id))
        if fmea_id is None or fmea_id != authorized_source.fmea_id:
            raise PermissionError('Recovery unavailable')
    return fmea_id


async def lock_restart_source(db, task, authorized_source):
    """Fence only the still-authorized source and proof metadata; never read nodes."""
    fmea_id = await require_restart_target_source(db, task, authorized_source)
    with db.no_autoflush:
        source = (await _no_wait(db, select(FMEADocument.fmea_id).where(
            FMEADocument.fmea_id == fmea_id))).scalar_one_or_none()
        if source is None:
            raise PermissionError('Recovery unavailable')
        for model, key in ((CapaD4RootCauseSourceProof, CapaD4RootCauseSourceProof.proof_id),
                           (CapaD4RootCauseRevision, CapaD4RootCauseRevision.revision_id)):
            await _no_wait(db, select(key).where(model.report_id == task.target_capa_id).order_by(key))
        await _no_wait(db, select(CapaRootCauseVerification.verification_id).where(
            CapaRootCauseVerification.capa_id == task.target_capa_id)
            .order_by(CapaRootCauseVerification.verification_id))


async def lock_restart_grants(db, task, installation):
    """Fence existing grants/scopes; parent row locks prevent FK insertions."""
    with db.no_autoflush:
        plugins = list((await _no_wait(db, select(AgentPluginGrant.grant_id).where(
            AgentPluginGrant.installation_id == installation.installation_id)
            .order_by(AgentPluginGrant.grant_id))).scalars().all())
        tasks = list((await _no_wait(db, select(AgentTaskGrant.grant_id).where(
            AgentTaskGrant.task_id == task.task_id).order_by(AgentTaskGrant.grant_id))).scalars().all())
        await _no_wait(db, select(AgentPluginDerivedSourceScope.plugin_grant_id).where(
            AgentPluginDerivedSourceScope.plugin_grant_id.in_(plugins))
            .order_by(AgentPluginDerivedSourceScope.plugin_grant_id))
        await _no_wait(db, select(AgentTaskDerivedSourceScope.task_grant_id).where(
            AgentTaskDerivedSourceScope.task_grant_id.in_(tasks))
            .order_by(AgentTaskDerivedSourceScope.task_grant_id))
        await _no_wait(db, select(D4TaskParentGrant.task_grant_id).where(
            D4TaskParentGrant.task_grant_id.in_(tasks)).order_by(D4TaskParentGrant.task_grant_id))
