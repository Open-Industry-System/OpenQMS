import pytest

from app.services.agent import harness
from app.services.agent.tools import demo


@pytest.mark.asyncio
async def test_list_fmea_documents_factory_scoped(db, admin_user, default_factory):
    # default_factory has no FMEAs seeded here -> empty result, but must not raise and must not leak
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    out = await demo.list_fmea_documents(ctx, page=1)
    assert "items" in out and "total" in out
    assert all(isinstance(x, str) for x in out["items"])  # fmea_id strings only


@pytest.mark.asyncio
async def test_draft_note_returns_text_or_empty_marker():
    ctx = object()  # draft_note does not touch ctx
    out = await demo.draft_note(ctx, text="hello")
    assert out == {"draft": "hello"}
    out2 = await demo.draft_note(ctx, text="")
    assert out2 == {"draft": "（空草稿）"}
