"""Known verification read restrictions; neither proof nor historic attestation."""
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import Text, and_, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
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


# Valid markers have at most 200 entries. Even worst-case JSON escaping is
# <200*(72 UUID bytes + 128*6 cause bytes + 20*6 line bytes + 128 syntax bytes),
# or 217600 bytes. 256 KiB preserves every valid marker while bounding legacy
# corruption. Size/shape flags remain separate from the nullable projection.
MAX_ORIGIN_METADATA_BYTES=256*1024
MAX_REF_METADATA_BYTES=4096
_UUID_PATTERN=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'


def _origin_shape(value):
    fields={key:value[key] for key in KEYS}
    expected=func.jsonb_build_object(*[item for key in sorted(KEYS) for item in (key,fields[key])])
    return and_(func.jsonb_typeof(value)=='object',value==expected,
        *[func.jsonb_typeof(fields[key])=='string' for key in KEYS],
        fields['kind'].astext=='fmea',fields['fmea_id'].astext.op('~')(_UUID_PATTERN),
        fields['factory_id'].astext.op('~')(_UUID_PATTERN),
        func.char_length(fields['cause_node_id'].astext).between(1,128),
        func.btrim(fields['cause_node_id'].astext)!='',
        func.char_length(fields['product_line_code'].astext).between(1,20),
        func.btrim(fields['product_line_code'].astext)!='')


async def known_origins(db,report_id,verification_id=None):
    model=CapaRootCauseVerification
    ref=model.source_ref
    marker=model.r6_source_origins
    ref_absent=or_(ref.is_(None),func.jsonb_typeof(ref)=='null')
    ref_size=func.coalesce(func.octet_length(cast(ref,Text)),0)<=MAX_REF_METADATA_BYTES
    ref_shape=and_(func.jsonb_typeof(ref)=='object',
        func.jsonb_typeof(ref['fmea_id'])=='string',func.jsonb_typeof(ref['cause_node_id'])=='string',
        ref==func.jsonb_build_object('fmea_id',ref['fmea_id'],'cause_node_id',ref['cause_node_id']),
        ref['fmea_id'].astext.op('~')(_UUID_PATTERN),
        func.char_length(ref['cause_node_id'].astext).between(1,128),
        func.btrim(ref['cause_node_id'].astext)!='')
    ref_valid=and_(ref_size,ref_shape)
    marker_absent=or_(marker.is_(None),func.jsonb_typeof(marker)=='null')
    marker_size=func.coalesce(func.octet_length(cast(marker,Text)),0)<=MAX_ORIGIN_METADATA_BYTES
    array=case((func.jsonb_typeof(marker)=='array',marker),else_=cast([],JSONB))
    elements=func.jsonb_array_elements(array).table_valued('value').alias('known_origin')
    item_shape=_origin_shape(cast(elements.c.value,JSONB))
    invalid_item=(select(1).select_from(elements)
        .where(or_(~item_shape,item_shape.is_(None))).correlate(model).exists())
    marker_shape=or_(marker_absent,and_(func.jsonb_typeof(marker)=='array',
        func.jsonb_array_length(array)<=200,~invalid_item))
    query=(select(model.verification_id,model.factory_id,
        marker_size.label('marker_size_ok'),marker_shape.label('marker_shape_ok'),
        case((and_(marker_size,marker_shape),marker),else_=None).label('origins'),
        ref_absent.label('ref_absent'),ref_size.label('ref_size_ok'),ref_shape.label('ref_shape_ok'),
        case((ref_valid,ref['fmea_id'].astext),else_=None).label('source_fmea_id'),
        case((ref_valid,ref['cause_node_id'].astext),else_=None).label('source_node_id'))
        .where(model.capa_id==report_id))
    if verification_id is not None: query=query.where(model.verification_id==verification_id)
    rows=(await db.execute(query)).all()
    result={}
    for row in rows:
        if row.marker_size_ok is not True or row.marker_shape_ok is not True:
            raise PermissionError(UNAVAILABLE)
        origins=validate_origins(row.origins)
        if not row.ref_absent:
            if row.ref_size_ok is not True or row.ref_shape_ok is not True:
                raise PermissionError(UNAVAILABLE)
            try:
                source_id=UUID(row.source_fmea_id)
                if str(source_id)!=row.source_fmea_id: raise ValueError()
            except (ValueError,TypeError): raise PermissionError(UNAVAILABLE) from None
            if (type(row.source_node_id) is not str or not row.source_node_id.strip()
                    or len(row.source_node_id)>128): raise PermissionError(UNAVAILABLE)
            parent=(await db.execute(select(FMEADocument.factory_id,FMEADocument.product_line_code)
                .where(FMEADocument.fmea_id==source_id))).one_or_none()
            if parent is None: raise PermissionError(UNAVAILABLE)
            current=dict(kind='fmea',fmea_id=str(source_id),cause_node_id=row.source_node_id,
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
