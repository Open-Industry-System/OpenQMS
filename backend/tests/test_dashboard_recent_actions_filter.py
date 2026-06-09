import os

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.dashboard_service import get_recent_actions


@pytest.mark.anyio
async def test_recent_actions_filters_ai_trend_interpret():
    audit_logs = [
        MagicMock(
            record_id="r1",
            table_name="quality_trends",
            action="AI_TREND_INTERPRET",
            operated_at=datetime.now(timezone.utc),
            operated_by="u1",
        ),
        MagicMock(
            record_id="r2",
            table_name="fmea_documents",
            action="UPDATE",
            operated_at=datetime.now(timezone.utc),
            operated_by="u1",
        ),
    ]
    db = AsyncMock()
    # SQLAlchemy async result chain: execute() is async, but result.scalars() and .all() are sync
    mock_scalar_result = MagicMock()
    mock_scalar_result.all.return_value = audit_logs
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalar_result
    db.execute.return_value = mock_result
    db.scalar.return_value = "FMEA-2026-001"

    actions = await get_recent_actions(db, user_id="u1", limit=5)

    # Verify the query passed to db.execute has the filter clauses.
    # Since we mock db.execute, we verify by inspecting the call argument.
    call_args = db.execute.call_args
    query = call_args[0][0]

    # Compile the query and inspect bind parameters to verify filter clauses
    compiled = query.compile()
    compiled_str = str(compiled)
    params = compiled.params

    assert "!=" in compiled_str or "<>" in compiled_str
    # The filter values should be in the bind parameters
    assert "AI_TREND_INTERPRET" in params.values()
    assert "quality_trends" in params.values()
