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
    db.refresh = AsyncMock()
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


# ─── FMEA optimistic locking tests ───

FMEA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _mock_for_update_result(lock_version: int):
    """构造 SELECT ... FOR UPDATE 查询的 mock 结果。"""
    fresh = MagicMock()
    fresh.lock_version = lock_version
    fresh.title = "Original Title"
    fresh.graph_data = {"nodes": [], "edges": []}
    fresh.product_line_code = "DC-DC-100"
    fresh.version = 1
    fresh.fmea_id = FMEA_ID
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = fresh
    return mock_result


@pytest.mark.asyncio
@patch("app.services.fmea_service.validate_product_line", new_callable=AsyncMock)
@patch("app.services.fmea_service.enqueue_embedding", new_callable=AsyncMock)
async def test_fmea_lock_version_mismatch(mock_embed, mock_validate):
    """传入 lock_version 与数据库不匹配时抛出异常。"""
    from app.services.fmea_service import update_fmea

    db = _create_mock_db()
    db.execute.return_value = _mock_for_update_result(lock_version=6)

    fmea = MagicMock()
    fmea.fmea_id = FMEA_ID
    fmea.lock_version = 5
    fmea.title = "Original Title"
    fmea.graph_data = {"nodes": [], "edges": []}
    fmea.product_line_code = "DC-DC-100"

    with pytest.raises(ValueError, match="lock_version_mismatch"):
        await update_fmea(
            db, fmea, title="New Title", graph_data=None,
            user_id=USER_ID, lock_version=5,
        )


@pytest.mark.asyncio
@patch("app.services.fmea_service.validate_product_line", new_callable=AsyncMock)
@patch("app.services.fmea_service.enqueue_embedding", new_callable=AsyncMock)
async def test_fmea_force_save_changed_again(mock_embed, mock_validate):
    """force save 时数据库版本再次变化，抛出异常。"""
    from app.services.fmea_service import update_fmea

    db = _create_mock_db()
    db.execute.return_value = _mock_for_update_result(lock_version=7)

    fmea = MagicMock()
    fmea.fmea_id = FMEA_ID
    fmea.lock_version = 5
    fmea.title = "Original Title"
    fmea.graph_data = {"nodes": [], "edges": []}
    fmea.product_line_code = "DC-DC-100"

    with pytest.raises(ValueError, match="lock_version_changed_again"):
        await update_fmea(
            db, fmea, title="New Title", graph_data=None,
            user_id=USER_ID, confirmed_latest_lock_version=6,
        )


@pytest.mark.asyncio
@patch("app.services.fmea_service.validate_product_line", new_callable=AsyncMock)
@patch("app.services.fmea_service.enqueue_embedding", new_callable=AsyncMock)
async def test_fmea_no_version_bump_when_no_actual_change(mock_embed, mock_validate):
    """没有实际变更时不递增 lock_version。"""
    from app.services.fmea_service import update_fmea

    db = _create_mock_db()
    db.execute.return_value = _mock_for_update_result(lock_version=5)

    fmea = MagicMock()
    fmea.fmea_id = FMEA_ID
    fmea.lock_version = 5
    fmea.title = "Original Title"
    fmea.graph_data = {"nodes": [], "edges": []}
    fmea.product_line_code = "DC-DC-100"

    await update_fmea(
        db, fmea, title="Original Title", graph_data=None,
        user_id=USER_ID, lock_version=5,
    )

    assert fmea.lock_version == 5
    # commit is still called because updated_by is set, but lock_version doesn't bump


@pytest.mark.asyncio
@patch("app.services.fmea_service.validate_product_line", new_callable=AsyncMock)
@patch("app.services.fmea_service.enqueue_embedding", new_callable=AsyncMock)
async def test_fmea_version_bumps_on_actual_change(mock_embed, mock_validate):
    """有实际变更时递增 lock_version。"""
    from app.services.fmea_service import update_fmea

    db = _create_mock_db()
    db.execute.return_value = _mock_for_update_result(lock_version=5)

    fmea = MagicMock()
    fmea.fmea_id = FMEA_ID
    fmea.lock_version = 5
    fmea.title = "Original Title"
    fmea.graph_data = {"nodes": [], "edges": []}
    fmea.product_line_code = "DC-DC-100"

    await update_fmea(
        db, fmea, title="Changed Title", graph_data=None,
        user_id=USER_ID, lock_version=5,
    )

    assert fmea.lock_version == 6
    db.commit.assert_called_once()
