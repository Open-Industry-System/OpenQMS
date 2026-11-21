"""Immutable pre-fusion sources for pre-switch legacy adoption.

Opaque capture IDs locate server records; client text/source/item_ref never
supplies historical authority. An unbound old suggestion must be regenerated.
"""
import hashlib
import hmac
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.capa_r6 import CapaR6LegacyCapture
from app.models.fmea import FMEADocument
from app.services.agent_runtime.d4_text_delivery import _digest


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


async def capture_sources(db, candidates, context, legacy_bindings, *, actor):
    from app.services.fmea_agent_sources import visible_fmea_source
    from app.models.capa import CAPAEightD
    result=[]
    for report_id,material in legacy_bindings:
        parent=await capa_metadata(db,UUID(str(report_id)))
        if parent is None:raise PermissionError('LEGACY_ORIGINAL_CAPA_SOURCE_UNBOUND')
        result.append({'kind':'capa','report_id':str(report_id),'material':material,
            'factory_id':str(parent.factory_id),'product_line':parent.product_line_code,'created_at':parent.created_at.isoformat()})
    ids = set()
    original_docs={str(doc['fmea_id']):doc for doc in context.fmea_docs or [] if doc.get('fmea_id')}
    # Historical CAPA witness is read in the same SQL statement as its body.
    from app.models.capa import CAPAEightD
    for item in candidates:
        for field in ('historical_capa_id','source_capa_id','capa_id'):
            source_id=item.metadata.get(field)
            if source_id:
                original=item.metadata.get('source_updated_at')
                current=await db.scalar(select(CAPAEightD.updated_at).where(CAPAEightD.report_id==UUID(str(source_id))))
                if original is None or current is None or current.isoformat()!= (original.isoformat() if hasattr(original,'isoformat') else original):
                    raise PermissionError('LEGACY_ORIGINAL_CAPA_SOURCE_UNBOUND')
    for item in candidates:
        value=item.metadata.get('fmea_id')
        if value:
            ids.add(UUID(str(value)))
    # The preloaded context may contribute to expansion/model enrichment even
    # when fusion discards the corresponding candidate metadata.
    for document in context.fmea_docs or []:
        if document.get('fmea_id'):
            ids.add(UUID(str(document['fmea_id'])))
    for source_id in sorted(ids,key=str):
        visible=await visible_fmea_source(db,SimpleNamespace(user=actor),source_id)
        row=(await db.execute(select(FMEADocument.factory_id,FMEADocument.product_line_code,
            FMEADocument.lock_version,FMEADocument.graph_data).where(FMEADocument.fmea_id==source_id))).one_or_none()
        if row is None or (row.factory_id,row.product_line_code)!=(visible.factory_id,visible.product_line_code):
            raise PermissionError('LEGACY_SOURCE_UNAVAILABLE')
        original=original_docs.get(str(source_id))
        if (original is None or type(original.get('lock_version')) is not int
            or original['lock_version']!=row.lock_version or _hash(original.get('graph_data'))!=_hash(row.graph_data)
            or str(original.get('factory_id'))!=str(row.factory_id) or original.get('product_line_code')!=row.product_line_code):
            raise PermissionError('LEGACY_ORIGINAL_FMEA_SOURCE_UNBOUND')
        result.append({'kind':'fmea','fmea_id':str(source_id),'factory_id':str(row.factory_id),
            'product_line':row.product_line_code,'version':row.lock_version,'graph_digest':_hash(row.graph_data)})
    if len(result)>999 or len(json.dumps(result).encode())>262144:
        raise PermissionError('LEGACY_SOURCE_SET_TOO_LARGE')
    return result


async def require_sources(db, sources, actor, *, lock=False):
    from app.models.capa import CAPAEightD
    from app.services.capa_d4_material import require_legacy_candidate_bindings
    from app.services.fmea_agent_sources import visible_fmea_source
    if not isinstance(sources,list) or len(sources)>1000:
        raise PermissionError('LEGACY_SOURCE_UNBOUND')
    capa_sources=[]
    for source in sources:
        if source.get('kind')=='capa' and set(source)=={'kind','report_id','material','factory_id','product_line','created_at'}:
            assert_capa_identity(source,await capa_metadata(db,UUID(source['report_id'])))
            capa_sources.append((source['report_id'],source['material']))
        elif source.get('kind')=='fmea' and set(source)=={'kind','fmea_id','factory_id','product_line','version','graph_digest'}:
            UUID(source['fmea_id'])
        elif source.get('kind')=='item' and set(source)=={'kind','source','stage_index','item_ref'}:
            if not isinstance(source['source'],str) or not isinstance(source['item_ref'],dict):
                raise PermissionError('LEGACY_SOURCE_UNBOUND')
        else:
            raise PermissionError('LEGACY_SOURCE_UNBOUND')
    # CAPA parents precede FMEA parents; target parent is held by adoption.
    if lock:
        for report_id,_ in sorted(capa_sources):
            await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==UUID(report_id)).with_for_update(nowait=True))
        for source in sorted((s for s in sources if s['kind']=='fmea'),key=lambda s:s['fmea_id']):
            await db.scalar(select(FMEADocument.fmea_id).where(FMEADocument.fmea_id==UUID(source['fmea_id'])).with_for_update(nowait=True))
    for source in sources:
        if source['kind']=='capa':assert_capa_identity(source,await capa_metadata(db,UUID(source['report_id'])))
    await require_legacy_candidate_bindings(db,capa_sources,actor=actor)
    for source in sources:
        if source['kind']!='fmea': continue
        visible=await visible_fmea_source(db,SimpleNamespace(user=actor),UUID(source['fmea_id']))
        row=(await db.execute(select(FMEADocument.lock_version,FMEADocument.graph_data).where(FMEADocument.fmea_id==visible.fmea_id))).one_or_none()
        if (str(visible.factory_id)!=source['factory_id'] or visible.product_line_code!=source['product_line']
            or row is None or row.lock_version!=source['version'] or _hash(row.graph_data)!=source['graph_digest']):
            raise PermissionError('LEGACY_SOURCE_CHANGED')


def _payload(row):
    return {key:str(getattr(row,key)) if key in {'capture_id','report_id','actor_id','tenant_id'} and getattr(row,key) is not None
        else getattr(row,key) for key in ('capture_id','report_id','actor_id','namespace','tenant_id','tenant_generation',
            'stage','text_digest','target_material','source_bindings')}


async def store(db, *, report_id, actor, stage, items, sources, target_material):
    if sources is None:
        raise PermissionError('LEGACY_SOURCE_UNBOUND')
    await require_sources(db,sources,actor)
    binding=db.info.get('tenant_binding')
    for item in items:
        row=CapaR6LegacyCapture(capture_id=uuid4(),report_id=report_id,actor_id=actor.user_id,
            namespace='single:public' if binding is None else binding.schema_name,
            tenant_id=None if binding is None else binding.tenant_id,tenant_generation=0 if binding is None else binding.generation,
            stage=stage,text_digest=_hash(item.content),target_material=target_material,source_bindings=[*sources,
                {'kind':'item','source':'rule' if item.source in {'rule_engine','rule_engine_measure'} else item.source,
                 'stage_index':item.metadata.get('stage_index'),'item_ref':{key:str(item.metadata[key]) for key in
                    ('fmea_id','failure_cause_node_id','failure_mode_node_id','control_node_id','historical_capa_id','source_capa_id','capa_id','entry_id','lesson_id') if item.metadata.get(key) is not None}}])
        row.binding_hmac=_digest('openqms.r6.legacy-capture.v1',_payload(row))
        db.add(row)
        item.metadata['capture_id']=str(row.capture_id)
    await db.flush()


async def capture_identity(db,capa,request):
    if request.capture_id is None:
        raise HTTPException(409,'LEGACY_CANDIDATE_REGENERATE_REQUIRED')
    row=await db.get(CapaR6LegacyCapture,request.capture_id,populate_existing=True)
    binding=db.info.get('tenant_binding')
    if (row is None or row.report_id!=capa.report_id or row.stage!=request.d_step
        or row.namespace!=('single:public' if binding is None else binding.schema_name)
        or row.tenant_id!=(None if binding is None else binding.tenant_id)
        or row.tenant_generation!=(0 if binding is None else binding.generation)
        or not hmac.compare_digest(row.binding_hmac,_digest('openqms.r6.legacy-capture.v1',_payload(row)))
        or row.text_digest!=_hash(request.adopted_text)):
        raise HTTPException(409,'LEGACY_CANDIDATE_REGENERATE_REQUIRED')
    return row


async def canonical_request(db,capa,request):
    if request.capture_id is None:
        return request
    row=await capture_identity(db,capa,request)
    items=[source for source in row.source_bindings if source.get('kind')=='item']
    if len(items)!=1:
        raise HTTPException(409,'LEGACY_CANDIDATE_REGENERATE_REQUIRED')
    item=items[0]
    return request.model_copy(update={'source':item['source'],'stage_index':item['stage_index'],
        'item_ref':dict(item['item_ref'],r6_capture_id=str(row.capture_id))})


async def require_capture(db,capa,request,actor):
    from app.services.capa_d4_material import material_version
    row=await capture_identity(db,capa,request)
    await require_sources(db,row.source_bindings,actor,lock=True)
    if row.target_material!=await material_version(db,capa.report_id):
        raise HTTPException(409,'LEGACY_CANDIDATE_REGENERATE_REQUIRED')
    if capa.status!= {'d4':'D4_ROOT_CAUSE','d5':'D5_CORRECTION'}[request.d_step]:
        raise HTTPException(409,'LEGACY_CANDIDATE_STAGE_CHANGED')
    return row


async def bound_captures(db,report_id,*,d_step=None):
    """Only metadata/digests are selected before original S is authorized."""
    from sqlalchemy import text
    rows=(await db.execute(text("""SELECT adoption_id,d_step,item_ref,
        encode(public.digest(to_jsonb(adopted_text)::text,'sha256'),'hex') AS text_digest
        FROM capa_ai_adoption WHERE capa_id=:report_id"""),{'report_id':report_id})).all()
    result=[]
    for adoption in rows:
        if d_step is not None and adoption.d_step!=d_step:continue
        ref=adoption.item_ref
        if not isinstance(ref,dict) or 'r6_capture_id' not in ref:continue
        try:identifier=UUID(ref['r6_capture_id'])
        except (ValueError,TypeError,AttributeError):raise PermissionError('LEGACY_CAPTURE_UNAVAILABLE') from None
        row=await db.get(CapaR6LegacyCapture,identifier,populate_existing=True)
        binding=db.info.get('tenant_binding')
        if (row is None or row.report_id!=report_id or row.stage!=adoption.d_step or row.text_digest!=adoption.text_digest
            or row.namespace!=('single:public' if binding is None else binding.schema_name)
            or row.tenant_id!=(None if binding is None else binding.tenant_id)
            or row.tenant_generation!=(0 if binding is None else binding.generation)
            or not hmac.compare_digest(row.binding_hmac,_digest('openqms.r6.legacy-capture.v1',_payload(row)))):
            raise PermissionError('LEGACY_CAPTURE_UNAVAILABLE')
        result.append(row)
    return result


async def authorize_bound_sources(db,actor_id,report_id,*,d_step=None,capture_id=None):
    """Historic versions remain historic; current authority is always required."""
    from app.services.capa_d4_material import authorize_root
    from app.services.fmea_agent_sources import visible_fmea_source
    stack=db.info.setdefault('r6_legacy_authorizing',set())
    identity=(report_id,d_step,capture_id)
    if identity in stack or len(stack)>=32:raise PermissionError('LEGACY_CAPTURE_CYCLE')
    stack.add(identity)
    try:
        rows=await bound_captures(db,report_id,d_step=d_step)
        if capture_id is not None:
            rows=[row for row in rows if row.capture_id==capture_id]
            if len(rows)!=1:raise PermissionError("LEGACY_CAPTURE_UNAVAILABLE")
        for row in rows:
            for source in row.source_bindings:
                if source['kind']=='capa':
                    parent=UUID(source['report_id'])
                    assert_capa_identity(source,await capa_metadata(db,parent))
                    await authorize_root(db,actor_id,parent)
                    await authorize_bound_sources(db,actor_id,parent,d_step='d5')
                elif source['kind']=='fmea':
                    visible=await visible_fmea_source(db,SimpleNamespace(user=SimpleNamespace(user_id=actor_id)),UUID(source['fmea_id']))
                    if (str(visible.factory_id),visible.product_line_code)!=(source['factory_id'],source['product_line']):
                        raise PermissionError('LEGACY_CAPTURE_SOURCE_UNAVAILABLE')
                elif source['kind']!='item':raise PermissionError('LEGACY_CAPTURE_SOURCE_UNAVAILABLE')
        return rows
    finally:stack.remove(identity)


async def require_ordinary_capture_material(db,report_id):
    if any(source['kind']!='item' for row in await bound_captures(db,report_id) for source in row.source_bindings):
        raise PermissionError('LEGACY_CAPTURE_FULL_DELIVERY_UNAVAILABLE: continue authorized manual work')


async def current_capture_material(db,report_id):
    """Opaque form metadata; no source/report body is selected."""
    from app.services.capa_d4_material import material_version
    stack=db.info.setdefault('r6_legacy_material_stack',set())
    if report_id in stack or len(stack)>=32:raise PermissionError('LEGACY_CAPTURE_CYCLE')
    stack.add(report_id)
    try:
        result=[]
        for row in await bound_captures(db,report_id):
            parents=[]
            for source in row.source_bindings:
                if source['kind']=='capa':
                    parent=await capa_metadata(db,UUID(source['report_id']))
                    parents.append(['capa',source['report_id'],None if parent is None else
                        [str(parent.factory_id),parent.product_line_code,parent.created_at.isoformat(),
                         await material_version(db,UUID(source['report_id']),include_entry_epoch=False)]])
                elif source['kind']=='fmea':
                    parent=(await db.execute(select(FMEADocument.lock_version,FMEADocument.factory_id,
                        FMEADocument.product_line_code).where(FMEADocument.fmea_id==UUID(source['fmea_id'])))).one_or_none()
                    parents.append(['fmea',source['fmea_id'],None if parent is None else [parent.lock_version,str(parent.factory_id),parent.product_line_code]])
            result.append([str(row.capture_id),row.stage,row.binding_hmac,parents])
        return result
    finally:stack.remove(report_id)


async def known_fmea_coordinates(db,report_id):
    return [dict(fmea_id=source['fmea_id'],factory_id=source['factory_id'],product_line_code=source['product_line'])
        for row in await bound_captures(db,report_id) for source in row.source_bindings if source['kind']=='fmea']


async def capa_metadata(db,report_id):
    from app.models.capa import CAPAEightD
    return (await db.execute(select(CAPAEightD.factory_id,CAPAEightD.product_line_code,CAPAEightD.created_at)
        .where(CAPAEightD.report_id==report_id))).one_or_none()


def assert_capa_identity(source,current):
    from datetime import datetime
    try:
        created=datetime.fromisoformat(source['created_at'].replace('Z','+00:00'))
        valid=(created.tzinfo is not None and current is not None and created==current.created_at
            and source['factory_id']==str(current.factory_id) and source['product_line']==current.product_line_code)
    except (KeyError,TypeError,ValueError,AttributeError):valid=False
    if not valid:raise PermissionError('LEGACY_CAPTURE_CAPA_IDENTITY_UNAVAILABLE')


async def known_capa_coordinates(db,report_id):
    values=[]
    for row in await bound_captures(db,report_id):
        for source in row.source_bindings:
            if source['kind']=='capa':
                if set(source)!={'kind','report_id','material','factory_id','product_line','created_at'}:
                    raise PermissionError('LEGACY_CAPTURE_CAPA_IDENTITY_UNAVAILABLE')
                values.append(dict(module='capa',object_id=source['report_id'],factory_id=source['factory_id'],
                    product_line_code=source['product_line'],created_at=source['created_at']))
    return values


async def lock_current_history_sources(db,actor_id,report_id):
    """Lock current full material without recapturing historical versions.

    The target identifier is already locked. CAPA parents use sorted NOWAIT
    locks; document parents use the existing shared global order. A source-set
    change while waiting requires a fresh request, never a stale body read.
    """
    from app.services.capa_r6_local_closure import source_coordinates,authorize_sources,lock_sources
    from app.services.capa_d4_material import authorize_root
    async def coordinates():
        seen=set();pending=[(report_id,0)];result={}
        while pending:
            current,depth=pending.pop()
            if current in seen:continue
            if depth>=32:raise PermissionError('LEGACY_CAPTURE_CYCLE')
            seen.add(current)
            await authorize_root(db,actor_id,current)
            await authorize_bound_sources(db,actor_id,current,d_step='d5')
            for source in await source_coordinates(db,current):
                key=(source['module'],source['object_id'])
                if key in result and result[key]!=source:raise PermissionError('LEGACY_CAPTURE_SOURCE_UNAVAILABLE')
                result[key]=source
                if source['module']=='capa':pending.append((UUID(source['object_id']),depth+1))
        return [result[key] for key in sorted(result)]
    before=await coordinates()
    await authorize_sources(db,actor_id,before)
    await lock_sources(db,before)
    await authorize_sources(db,actor_id,before)
    if await coordinates()!=before:
        raise HTTPException(409,'LEGACY_CAPTURE_CURRENT_SOURCES_CHANGED_REFRESH')
