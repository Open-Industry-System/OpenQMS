import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-collaboration-tests")

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.collaboration_service import (
    upsert_session,
    delete_session,
    get_active_users,
    delete_expired_sessions,
)
from app.models.collaboration_session import CollaborationSession


DOC_ID = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
USER_ID = uuid.uuid4()


def _create_mock_db():
    """创建 mock AsyncSession，与 test_audit.py 风格一致。"""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_session_result(sessions: list):
    """构造 db.execute().scalars().all() 的 mock 链。"""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = sessions
    mock_result.scalars.return_value = mock_scalars
    return mock_result


@pytest.mark.asyncio
async def test_upsert_session_calls_execute_and_commit():
    """验证 heartbeat 会执行 SQL 并提交。"""
    db = _create_mock_db()
    db.execute.return_value = MagicMock()

    await upsert_session(
        db, "fmea", DOC_ID,
        user_id=USER_ID, user_name="张三", action="viewing", editing_area=None
    )

    db.execute.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_users_filters_expired():
    """验证 TTL 过滤：只返回 60 秒内活跃的用户。"""
    db = _create_mock_db()

    active_session = CollaborationSession(
        document_type="fmea", document_id=DOC_ID,
        user_id=USER_ID, user_name="张三", action="viewing",
        last_activity=datetime.now(timezone.utc),
    )
    db.execute.return_value = _mock_session_result([active_session])

    users = await get_active_users(db, "fmea", DOC_ID)

    assert len(users) == 1
    assert users[0].user_name == "张三"
    # 验证查询条件包含 last_activity
    executed_stmt = db.execute.call_args[0][0]
    assert "last_activity" in str(executed_stmt)


@pytest.mark.asyncio
async def test_delete_expired_sessions():
    """验证清理函数执行 delete 并返回删除计数。"""
    db = _create_mock_db()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    db.execute.return_value = mock_result

    deleted = await delete_expired_sessions(db)

    assert deleted == 3
    db.commit.assert_called_once()
