"""ERP dedicated dependency: API Key auth for /api/erp/ingest."""
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.erp import ERPConnection
from app.services.erp_crypto import hash_api_key


async def require_erp_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ERPConnection:
    """Validate X-API-Key header, return ERPConnection.

    ERP client must send X-Connection-Id header (full connection_id UUID),
    used for primary key O(1) lookup instead of scanning all connections.
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    raw_conn_id = request.headers.get("X-Connection-Id")
    if not raw_conn_id:
        raise HTTPException(status_code=401, detail="Missing X-Connection-Id header")

    # Parse as UUID — rejects malformed values immediately
    try:
        conn_id = uuid.UUID(raw_conn_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-Connection-Id format")

    # Primary key lookup — O(1), uses clustered index
    conn = await db.get(ERPConnection, conn_id)
    if not conn:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    auth_config = conn.config.get("auth_config", {})
    stored_hash = auth_config.get("api_key_hash")
    computed_hash = hash_api_key(api_key)
    if not stored_hash or stored_hash != computed_hash:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    if not conn.is_active:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return conn