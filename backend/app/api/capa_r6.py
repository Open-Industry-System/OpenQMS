"""Authenticated employee R6 review endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from app.core.deps import get_request_scope, RequestScope
from app.database import get_db
from app.schemas.capa_r6 import D4Confirm, D5Correct
from app.schemas.capa_d5_staff import D5Withdraw
from app.services import capa_sources_view as sources_service
from app.services.capa_review_guard import ReviewedContentLocked
from app.services import capa_d4_confirmation as service
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy

from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError

class ContentSafeR6Route(APIRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def guarded(request:Request):
            try:
                raw=bytearray()
                async for chunk in request.stream():
                    if len(raw)+len(chunk)>65536:
                        return JSONResponse({'detail':'R6 input limit'},status_code=413,headers={'Cache-Control':'no-store'})
                    raw.extend(chunk)
                request._body=bytes(raw)
                response=await handler(request)
                response.headers['Cache-Control']='no-store'
                return response
            except HTTPException as error:
                error.headers={**(error.headers or {}),'Cache-Control':'no-store'}
                raise
            except RequestValidationError:
                return JSONResponse({'detail':'R6 input invalid'},status_code=422,headers={'Cache-Control':'no-store'})
        return guarded

router=APIRouter(prefix='/api/capa/{report_id}',tags=['capa-r6'],route_class=ContentSafeR6Route)

async def call(db, function, *args):
    try:
        result=await function(db,*args)
        return JSONResponse(jsonable_encoder(result),headers={'Cache-Control':'no-store'})
    except (PermissionError,LookupError,ValueError,ControlFenceBusy,ReviewedContentLocked,DBAPIError) as error:
        await db.rollback()
        status=403 if isinstance(error,PermissionError) else 404 if isinstance(error,LookupError) else 409
        if isinstance(error,DBAPIError) and getattr(error.orig,'sqlstate',None) not in {'55P03','40001','40P01','23505'}:
            status=500
        raise HTTPException(status_code=status,detail='R6 item unavailable' if status!=409 else 'R6 material changed',
            headers={'Cache-Control':'no-store'}) from None

@router.get('/d4-candidates')
async def candidates(report_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,service.list_candidates,scope,report_id,page,page_size)

@router.post('/d4-candidates/{candidate_id}/confirm')
async def confirm(report_id:UUID,candidate_id:UUID,body:D4Confirm,
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,service.confirm,scope,report_id,candidate_id,body)

@router.get('/sources/{kind}/{item_id}')
async def sources(report_id:UUID,kind:str,item_id:UUID,
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,sources_service.source_details,scope,report_id,kind,item_id)

@router.get('/sources/{kind}/{item_id}/evidence/{source_id}')
async def evidence(report_id:UUID,kind:str,item_id:UUID,source_id:UUID,
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,sources_service.evidence,scope,report_id,kind,item_id,source_id)

@router.get('/legacy-adoptions')
async def legacy(report_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,sources_service.legacy_adoptions,scope,report_id,page,page_size)

@router.post('/d4-candidates/{candidate_id}/withdraw')
async def withdraw(report_id:UUID,candidate_id:UUID,body:D5Withdraw,
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,service.withdraw,scope,report_id,candidate_id,body)

@router.post('/d5-measures/{measure_id}/corrections')
async def correct_measure(report_id:UUID,measure_id:UUID,body:D5Correct,
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_d5_corrections import correct
    return await call(db,correct,scope,report_id,measure_id,body)

@router.get('/d5-measures/{measure_id}/corrections')
async def measure_history(report_id:UUID,measure_id:UUID,
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_d5_corrections import history
    return await call(db,history,scope,report_id,measure_id)

@router.get('/local-closure')
async def local_closure(report_id:UUID,scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_r6_local_closure import read
    return await call(db,read,scope,report_id)

from app.schemas.capa_r6 import LocalPrevention, LocalReason, ManualDocAnalysis

@router.post('/local-prevention')
async def local_prevention(report_id:UUID,body:LocalPrevention,scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_r6_local_closure import save_prevention
    return await call(db,save_prevention,scope,report_id,body)

@router.post('/manual-doc-analysis')
async def manual_doc_analysis(report_id:UUID,body:ManualDocAnalysis,scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_r6_local_closure import save_manual
    return await call(db,save_manual,scope,report_id,body)

@router.post('/propagation-review')
async def propagation_review(report_id:UUID,body:LocalReason,scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_r6_local_closure import save_propagation
    return await call(db,save_propagation,scope,report_id,body)

@router.get('/local-closure/history/{kind}')
async def local_history(report_id:UUID,kind:str,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),
        scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_r6_local_closure import history
    return await call(db,history,scope,report_id,kind,page,page_size)


@router.get('/d4-candidates/{candidate_id}/confirmation-context')
async def confirmation_context(report_id:UUID,candidate_id:UUID,scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    return await call(db,service.confirmation_context,scope,report_id,candidate_id)

@router.get('/manual-doc-catalog')
async def manual_catalog(report_id:UUID,scope:RequestScope=Depends(get_request_scope),db=Depends(get_db)):
    from app.services.capa_r6_local_closure import manual_catalog
    return await call(db,manual_catalog,scope,report_id)
