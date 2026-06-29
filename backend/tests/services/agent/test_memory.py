import pytest
import pytest_asyncio

from app.services.agent import harness, memory
from app.services.agent.tools import demo  # noqa

_redis_available: bool | None = None


async def _check_redis_available() -> bool:
    """Return True if Redis is reachable, False otherwise."""
    global _redis_available
    if _redis_available is not None:
        return _redis_available
    try:
        from redis.asyncio import Redis

        from app.config import settings

        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis.ping()
        await redis.close()
        _redis_available = True
    except Exception:
        _redis_available = False
    return _redis_available


@pytest_asyncio.fixture
async def redis_client():
    """Yield a Redis client if available, otherwise skip the test."""
    if not await _check_redis_available():
        pytest.skip("Redis not available")
    from redis.asyncio import Redis

    from app.config import settings

    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.close()


@pytest.mark.asyncio
async def test_remember_enqueues_queued_status(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    m = await memory.remember(db, ctx, kind="preference", content="用户偏好简短 8D 报告")
    assert m.embedding_status == "queued"
    assert m.factory_id == default_factory.id


@pytest.mark.asyncio
async def test_recall_fallback_matches_content(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    await memory.remember(db, ctx, kind="preference", content="用户偏好简短 8D 报告")
    hits = await memory.recall_fallback(db, default_factory.id, admin_user.user_id, "8D")
    assert any("8D" in h.content for h in hits)


@pytest.mark.asyncio
async def test_task_state_roundtrip(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    await memory.set_task_state(db, s, {"todo": ["d1", "d2"]})
    state = await memory.get_task_state(db, s)
    assert state["todo"] == ["d1", "d2"]


@pytest.mark.asyncio
async def test_short_term_roundtrip(redis_client, admin_user, default_factory):
    import uuid

    session_id = uuid.uuid4()
    msg = {"role": "user", "content": "hello"}
    await memory.push_short_term(
        redis_client, default_factory.id, admin_user.user_id, session_id, msg
    )
    items = await memory.get_short_term(
        redis_client, default_factory.id, admin_user.user_id, session_id
    )
    assert items == [msg]


@pytest.mark.asyncio
async def test_short_term_noop_when_redis_none(admin_user, default_factory):
    import uuid

    session_id = uuid.uuid4()
    # Should not raise even with redis=None
    await memory.push_short_term(
        None, default_factory.id, admin_user.user_id, session_id, {"role": "user"}
    )
    assert await memory.get_short_term(None, default_factory.id, admin_user.user_id, session_id) == []
