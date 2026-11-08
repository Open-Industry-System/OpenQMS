"""Fixed HTTP mappings for CAPA outcome-review conflicts."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.capa_review_guard import (
    OutcomeReviewConflict,
    OutcomeReviewLimit,
    OutcomeReviewRequired,
    ReviewedContentLocked,
)

_REVIEW_ERRORS = {
    ReviewedContentLocked: "CAPA_REVIEWED_CONTENT_LOCKED",
    OutcomeReviewConflict: "CAPA_OUTCOME_REVIEW_CHANGED",
    OutcomeReviewRequired: "CAPA_OUTCOME_REVIEW_REQUIRED",
    OutcomeReviewLimit: "CAPA_OUTCOME_REVIEW_LIMIT",
}


async def _review_error_handler(request: Request, exc: RuntimeError):
    for error_type, detail in _REVIEW_ERRORS.items():
        if isinstance(exc, error_type):
            return JSONResponse(status_code=409, content={"detail": detail})
    raise exc


def register_capa_review_errors(app: FastAPI) -> None:
    for error_type in _REVIEW_ERRORS:
        app.add_exception_handler(error_type, _review_error_handler)
