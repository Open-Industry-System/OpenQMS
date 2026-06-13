"""MES dedicated dependency: API Key auth for /api/mes/ingest."""
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.mes import MESConnection
from app.services.mes_crypto import verify_api_key


async def require_mes_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MESConnection:
    """Validate X-API-Key header, return MESConnection.

    MES client must send X-Connection-Id header (full connection_id UUID),
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
    conn = await db.get(MESConnection, conn_id)
    if not conn:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    auth_config = conn.config.get("auth_config", {})
    stored_hash = auth_config.get("api_key_hash")
    if not stored_hash or not verify_api_key(api_key, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid API Key")
    if not conn.is_active:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return conn
