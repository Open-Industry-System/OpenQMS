"""Known verification read restrictions; neither proof nor historic attestation."""
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import select
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.services.capa_current_access import current_capa_actor_access, current_capa_target_metadata
from app.services.fmea_agent_sources import visible_fmea_source

UNAVAILABLE='Verification sources unavailable'
KEYS={'kind','fmea_id','cause_node_id','factory_id','product_line_code'}


def validate_origins(value):
    if value is None: return []
    if type(value) is not list or len(value)>200: raise PermissionError(UNAVAILABLE)
    result=[]
    seen=set()
    for origin in value:
        if type(origin) is not dict or set(origin)!=KEYS or origin['kind']!='fmea': raise PermissionError(UNAVAILABLE)
        for key in ('fmea_id','factory_id'):
            try:
                if type(origin[key]) is not str or str(UUID(origin[key]))!=origin[key]: raise ValueError()
            except (ValueError,TypeError): raise PermissionError(UNAVAILABLE) from None
        if (type(origin['cause_node_id']) is not str or not origin['cause_node_id'].strip() or len(origin['cause_node_id'])>128
                or type(origin['product_line_code']) is not str or not origin['product_line_code'].strip()
                or len(origin['product_line_code'])>20): raise PermissionError(UNAVAILABLE)
        key=(origin['fmea_id'],origin['cause_node_id'])
        if key in seen: raise PermissionError(UNAVAILABLE)
        seen.add(key)
        result.append(origin)
    return result


async def known_origins(db,report_id,verification_id=None):
    query=select(CapaRootCauseVerification.verification_id,CapaRootCauseVerification.factory_id,
        CapaRootCauseVerification.source_ref,CapaRootCauseVerification.r6_source_origins).where(CapaRootCauseVerification.capa_id==report_id)
    if verification_id is not None: query=query.where(CapaRootCauseVerification.verification_id==verification_id)
    rows=(await db.execute(query)).all()
    result={}
    for row in rows:
        origins=validate_origins(row.r6_source_origins)
        ref=row.source_ref
        if ref is not None:
            if (type(ref) is not dict or set(ref)!={'fmea_id','cause_node_id'} or type(ref['fmea_id']) is not str
                    or type(ref['cause_node_id']) is not str or not ref['cause_node_id'].strip() or len(ref['cause_node_id'])>128):
                raise PermissionError(UNAVAILABLE)
            try:
                source_id=UUID(ref['fmea_id'])
                if str(source_id)!=ref['fmea_id']: raise ValueError()
            except (ValueError,TypeError): raise PermissionError(UNAVAILABLE) from None
            parent=(await db.execute(select(FMEADocument.factory_id,FMEADocument.product_line_code)
                .where(FMEADocument.fmea_id==source_id))).one_or_none()
            if parent is None: raise PermissionError(UNAVAILABLE)
            current=dict(kind='fmea',fmea_id=str(source_id),cause_node_id=ref['cause_node_id'],
                factory_id=str(parent.factory_id),product_line_code=parent.product_line_code)
            if current not in origins: origins=origins+[current]
        result[row.verification_id]=(row.factory_id,origins)
    return result


async def authorize_verifications(db,report_id,*,actor_id=None,access=None,verification_id=None,lock=False):
    if actor_id is not None:
        factories,lines=await current_capa_actor_access(db,actor_id,PermissionLevel.VIEW)
        target=await current_capa_target_metadata(db,report_id,factories,lines)
    elif access is not None:
        levels,factories,lines=access
        if levels.get(Module.CAPA,PermissionLevel.NONE)<PermissionLevel.VIEW: raise PermissionError(UNAVAILABLE)
        target=await current_capa_target_metadata(db,report_id,factories,lines)
    else: target=None
    origins=await known_origins(db,report_id,verification_id)
    async def check(values):
        for factory_id,sources in values.values():
            if target is not None and factory_id!=target.factory_id: raise PermissionError(UNAVAILABLE)
            for source in sources:
                if actor_id is not None:
                    visible=await visible_fmea_source(db,SimpleNamespace(user=SimpleNamespace(user_id=actor_id)),UUID(source['fmea_id']))
                elif access is not None:
                    levels,factories,lines=access
                    if (levels.get(Module.FMEA,PermissionLevel.NONE)<PermissionLevel.VIEW
                            or (factories.accessible_factory_ids is not None and UUID(source['factory_id']) not in factories.accessible_factory_ids)
                            or (lines.mode!='ALL' and source['product_line_code'] not in (lines.codes or []))): raise PermissionError(UNAVAILABLE)
                    visible=(await db.execute(select(FMEADocument.factory_id,FMEADocument.product_line_code)
                        .where(FMEADocument.fmea_id==UUID(source['fmea_id'])))).one_or_none()
                else: raise PermissionError(UNAVAILABLE)
                if visible is None or (str(visible.factory_id),visible.product_line_code)!=(source['factory_id'],source['product_line_code']):
                    raise PermissionError(UNAVAILABLE)
    await check(origins)
    if lock:
        for source_id in sorted({s['fmea_id'] for _,values in origins.values() for s in values}):
            await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==UUID(source_id)).with_for_update(nowait=True))
        from app.services.agent_runtime.control_authority_fence import lock_employee_acl
        await lock_employee_acl(db,(actor_id,))
        origins=await known_origins(db,report_id,verification_id)
        await check(origins)
    return [s for _,values in origins.values() for s in values]


async def require_legacy_verifications_only(db,report_id):
    """Old model review has no delivery contract for known verification sources."""
    if any(values for _,values in (await known_origins(db,report_id)).values()):
        raise PermissionError('D4_VERIFICATION_DELIVERY_UNAVAILABLE')
