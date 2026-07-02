"""E2E-only endpoints. Registered only when E2E_MODE and not production.

Provides a read-only seed-state view and a whitelist-based cleanup for test data.
Never exposed in production (gated at router registration in main.py)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


@router.get("/seed-state")
async def get_seed_state(db: AsyncSession = Depends(get_db)):
    """Return known seed records (factories, product lines, accounts, doc numbers + ids)."""
    # Implemented in Task 3.
    raise NotImplementedError


@router.post("/cleanup")
async def cleanup_test_data(prefix: str = Query(..., min_length=4, max_length=20), db: AsyncSession = Depends(get_db)):
    """Delete test data whose doc_no/name starts with `prefix` (e.g. E2E-M1).
    Whitelist-based, FK-ordered, single transaction. Implemented in Task 4."""
    # Implemented in Task 4.
    raise NotImplementedError
