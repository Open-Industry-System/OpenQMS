"""Ordinary employee-only D4 candidates with bounded, content-safe request handling."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse

from app.config import settings
from app.core.deps import RequestScope, get_request_scope
from app.core.tenant_transaction import TenantUnavailable
from app.database import get_db
from app.schemas.capa_d4_text_preview import D4PreviewAvailability, D4PreviewRequest, D4PreviewVersion, D4TextPreview
from app.services import capa_d4_text_preview as service


class EmptyQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ContentSafePreviewRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def guarded(request: Request):
            if not settings.CAPA_D4_TEXT_PREVIEW_ENABLED:
                return JSONResponse(status_code=404, content={'detail':'Not Found'})
            try:
                raw = bytearray()
                async for chunk in request.stream():
                    if len(raw)+len(chunk) > 64*1024:
                        return JSONResponse(status_code=413, content={'detail':'PREVIEW_INPUT_LIMIT'})
                    raw.extend(chunk)
                request._body = bytes(raw)
                if request.method == 'GET' and raw:
                    return JSONResponse(status_code=422, content={'detail':'PREVIEW_INPUT_INVALID'})
                return await handler(request)
            except RequestValidationError:
                # The framework's default errors contain input values, including private terms.
                return JSONResponse(status_code=422, content={'detail':'PREVIEW_INPUT_INVALID'})
            except HTTPException:
                raise
            except Exception:
                # Never log SQL, input, candidate content or wire exception details here.
                return JSONResponse(status_code=500, content={'detail':'PREVIEW_UNAVAILABLE'})
        return guarded


router = APIRouter(prefix='/api/capa/{report_id}/d4-text-preview', tags=['capa-d4-text-preview'],
    route_class=ContentSafePreviewRoute)


async def _call(db, function, *args):
    try:
        return await function(db, *args)
    except (PermissionError, TenantUnavailable):
        await db.rollback()
        raise HTTPException(status_code=403, detail='PREVIEW_ACCESS_DENIED') from None
    except LookupError:
        await db.rollback()
        raise HTTPException(status_code=404, detail='Not Found') from None
    except service.PreviewSourceLimit:
        await db.rollback()
        raise HTTPException(status_code=409, detail='PREVIEW_SOURCE_LIMIT') from None
    except service.PreviewConflict:
        await db.rollback()
        raise HTTPException(status_code=409, detail='PREVIEW_SOURCE_CHANGED') from None
    except ValueError:
        await db.rollback()
        raise HTTPException(status_code=422, detail='PREVIEW_INPUT_INVALID') from None


@router.get('/availability', response_model=D4PreviewAvailability)
async def availability(report_id: UUID, query: EmptyQuery = Query(),
                       scope: RequestScope = Depends(get_request_scope), db=Depends(get_db)):
    return await _call(db, service.availability, scope, report_id)


@router.get('/version', response_model=D4PreviewVersion)
async def version(report_id: UUID, query: EmptyQuery = Query(),
                  scope: RequestScope = Depends(get_request_scope), db=Depends(get_db)):
    return await _call(db, service.get_version, scope, report_id)


@router.post('', response_model=D4TextPreview)
async def preview(report_id: UUID, body: D4PreviewRequest, query: EmptyQuery = Query(),
                  scope: RequestScope = Depends(get_request_scope), db=Depends(get_db)):
    return await _call(db, service.create_preview, scope, report_id, body)
