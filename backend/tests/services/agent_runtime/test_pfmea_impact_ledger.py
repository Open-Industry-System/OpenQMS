"""R7 accounting tests. Runtime authorization and transport are separate fences."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.agent_runtime.pfmea_impact_release import (
    PageConfirmationMismatch,
    PageScope,
    ProjectionBudgetExceeded,
    verify_page_payload,
)


def test_budget_reconstructed_from_all_potentially_released_attempts():
    from app.services.agent_runtime.pfmea_impact_ledger import fmea_usage_from_releases
    from app.services.agent_runtime.pfmea_impact_release import reserve_fmea_release

    rows = [SimpleNamespace(kind="release", payload={
        "module": "fmea", "byte_count": 8, "element_keys": ["step", "cause"],
    }) for _ in range(16)]
    rows += [
        SimpleNamespace(kind="page_confirmation", payload={}),
        SimpleNamespace(kind="release", payload={"module": "capa", "byte_count": 1000}),
    ]
    usage = fmea_usage_from_releases(rows)
    assert (usage.attempts, usage.byte_count, usage.element_keys) == (16, 128, {"step", "cause"})
    with pytest.raises(ProjectionBudgetExceeded):
        reserve_fmea_release(usage, projection_bytes=b"next", element_keys=("step",))


@pytest.mark.parametrize("bad", [True, -1, "8", None])
def test_invalid_persisted_release_cannot_lower_usage(bad):
    from app.services.agent_runtime.pfmea_impact_ledger import fmea_usage_from_releases

    rows = [SimpleNamespace(kind="release", payload={
        "module": "fmea", "byte_count": bad, "element_keys": ["step"],
    })]
    with pytest.raises(PermissionError):
        fmea_usage_from_releases(rows)


def test_scope_digest_separates_page_coordinates():
    from dataclasses import replace
    from app.services.agent_runtime.pfmea_impact_ledger import scope_digest

    original = PageScope(uuid4(), uuid4(), 3, "binding", "snapshot", "OP40")
    other_scopes = (
        replace(original, task_id=uuid4()), replace(original, run_id=uuid4()),
        replace(original, lease_epoch=4), replace(original, binding_digest="other"),
        replace(original, snapshot_digest="other"), replace(original, scope_ref="OP41"),
    )
    assert len({scope_digest(original), *(scope_digest(other) for other in other_scopes)}) == 7


def test_page_receipt_rejects_retry_bytes_that_do_not_match_server_plan():
    from app.services.agent_runtime.pfmea_impact_ledger import make_release_payload

    scope = PageScope(uuid4(), uuid4(), 3, "binding", "snapshot", "OP40")
    from hashlib import sha256
    digests = {"first": sha256(b"trusted").hexdigest()}
    with pytest.raises(PageConfirmationMismatch):
        make_release_payload(scope, module="fmea", body=b"changed", element_keys=("step",),
                             sources=(), page_key="first", expected_page_digests=digests)
    payload = make_release_payload(scope, module="fmea", body=b"trusted", element_keys=("step", "step"),
                                   sources=(), page_key="first", expected_page_digests=digests)
    assert payload["payload_digest"] == verify_page_payload(
        "first", b"trusted", expected_page_digests=digests)
    assert payload["element_keys"] == ["step"]
    assert payload["byte_count"] == 7
    assert b"trusted" not in repr(payload).encode()


async def _registered_scope(runtime):
    from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding
    from app.models.agent_task import AgentTask
    from app.schemas.pfmea_impact import ImpactSourceRef

    async with runtime.factory(binding=runtime.binding) as db:
        task = await db.get(AgentTask, runtime.task_id)
        db.add(AgentPfmeaImpactBinding(
            task_id=task.task_id, actor_id=task.initiator_id, request_key=task.request_key,
            binding={"schema_version": 1}, binding_digest="a" * 64,
        ))
        sources = (ImpactSourceRef(source_id=uuid4(), module="fmea", object_id=uuid4(),
            projection_id="fmea.pfmea_impact.snapshot.v1", version="b" * 64,
            factory_id=task.factory_id, product_line_code="DC-DC-100"),)
        await db.commit()
    return PageScope(runtime.task_id, runtime.run_id, 0, "a" * 64, "b" * 64, "scope-1"), sources


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["attempts", "elements", "bytes"])
async def test_concurrent_final_budget_unit_is_reserved_exactly_once(committed_runtime, limit):
    import asyncio

    from sqlalchemy import func, select

    from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt
    from app.services.agent_runtime.pfmea_impact_ledger import record_release
    from app.services.agent_runtime.pfmea_impact_release import FMEA_MAX_BYTES

    runtime = committed_runtime
    scope, sources = await _registered_scope(runtime)
    async with runtime.factory(binding=runtime.binding) as db:
        if limit == "attempts":
            for _ in range(15):
                await record_release(db, scope, module="fmea", body=b"x", element_keys=(), sources=sources)
            before = 15
        else:
            await record_release(
                db, scope, module="fmea",
                body=b"x" * (FMEA_MAX_BYTES - 1) if limit == "bytes" else b"x",
                element_keys=tuple(str(i) for i in range(199)) if limit == "elements" else (),
                sources=sources,
            )
            before = 1
        await db.commit()

    start = asyncio.Event()
    ready = asyncio.Queue()

    async def request(element):
        async with runtime.factory(binding=runtime.binding) as db:
            ready.put_nowait(None)
            await start.wait()
            try:
                await record_release(db, scope, module="fmea", body=b"x",
                                     element_keys=(element,), sources=sources)
            except ProjectionBudgetExceeded:
                await db.rollback()
                return False
            await db.commit()
            return True

    workers = [asyncio.create_task(request(element)) for element in ("candidate-1", "candidate-2")]
    try:
        await asyncio.wait_for(ready.get(), timeout=5)
        await asyncio.wait_for(ready.get(), timeout=5)
        start.set()
        assert sorted(await asyncio.wait_for(asyncio.gather(*workers), timeout=20)) == [False, True]
    finally:
        for worker in workers:
            if not worker.done():
                worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async with runtime.factory(binding=runtime.binding) as db:
        count = await db.scalar(select(func.count()).select_from(AgentPfmeaImpactReceipt).where(
            AgentPfmeaImpactReceipt.run_id == scope.run_id, AgentPfmeaImpactReceipt.kind == "release",
        ))
        assert count == before + 1


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_failed_send_stays_in_source_ledger_but_only_confirmed_pages_prove_coverage(committed_runtime):
    from hashlib import sha256

    from sqlalchemy import select

    from app.models.agent_pfmea_impact import AgentPfmeaImpactReceipt
    from app.services.agent_runtime.pfmea_impact_ledger import (
        fmea_usage_from_releases, record_confirmation, record_coverage, record_release,
        sign_page_confirmation_token,
    )

    runtime = committed_runtime
    scope, sources = await _registered_scope(runtime)
    one, two = "1" * 64, "2" * 64
    digests = {one: sha256(b"first").hexdigest(), two: sha256(b"second").hexdigest()}

    async def release(key, body):
        async with runtime.factory(binding=runtime.binding) as db:
            receipt_id = await record_release(db, scope, module="fmea", body=body,
                element_keys=(key,), sources=sources, page_key=key, expected_page_digests=digests)
            await db.commit()
            return receipt_id

    async def acknowledge(receipt_id, key):
        async with runtime.factory(binding=runtime.binding) as db:
            confirmation_id = await record_confirmation(db, scope, release_id=receipt_id,
                page_key=key, payload_digest=digests[key],
                token=sign_page_confirmation_token(scope, receipt_id, key, digests[key]),
                expected_page_digests=digests)
            await db.commit()
            return confirmation_id

    await release(one, b"first")  # No ACK: this send is still charged.
    retry = await release(one, b"first")
    confirmation = await acknowledge(retry, one)
    assert await acknowledge(retry, one) == confirmation
    second = await release(two, b"second")
    async with runtime.factory(binding=runtime.binding) as db:
        with pytest.raises(PageConfirmationMismatch, match="Incomplete"):
            await record_coverage(db, scope, expected_page_digests=digests)
    await acknowledge(second, two)
    async with runtime.factory(binding=runtime.binding) as db:
        coverage_id = await record_coverage(db, scope, expected_page_digests=digests)
        await db.commit()
    async with runtime.factory(binding=runtime.binding) as db:
        assert await record_coverage(db, scope, expected_page_digests=digests) == coverage_id
        rows = (await db.scalars(select(AgentPfmeaImpactReceipt).where(
            AgentPfmeaImpactReceipt.run_id == scope.run_id))).all()
        releases = [row for row in rows if row.kind == "release"]
        assert len(releases) == 3
        assert fmea_usage_from_releases(rows).attempts == 3
        assert all(row.payload["sources"] == [sources[0].model_dump(mode="json")] for row in releases)
        assert len([row for row in rows if row.kind == "page_confirmation"]) == 2


def test_page_confirmation_token_binds_release_page_bytes_and_current_epoch():
    from dataclasses import replace

    from app.services.agent_runtime.pfmea_impact_ledger import (
        require_page_confirmation_token,
        sign_page_confirmation_token,
    )

    scope = PageScope(uuid4(), uuid4(), 5, "binding", "snapshot", "OP40")
    release_id = uuid4()
    page, digest = "1" * 64, "2" * 64
    token = sign_page_confirmation_token(scope, release_id, page, digest)
    require_page_confirmation_token(scope, release_id, page, digest, token)
    for args in (
        (replace(scope, lease_epoch=6), release_id, page, digest),
        (replace(scope, scope_ref="OP41"), release_id, page, digest),
        (scope, uuid4(), page, digest),
        (scope, release_id, "3" * 64, digest),
        (scope, release_id, page, "3" * 64),
    ):
        with pytest.raises(PageConfirmationMismatch):
            require_page_confirmation_token(*args, token)
