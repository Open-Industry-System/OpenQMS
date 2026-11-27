"""Real HTTP releases the R7 detail and exact evidence under a current ACL fence."""

import asyncio

import pytest
from sqlalchemy import select, text, update

from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.services.agent_runtime import pfmea_impact_history as history
from tests.e2e.test_r7_pfmea_impact_process import (  # noqa: F401
    adopted_case,
    d4_text_local_trial,
    native_impact,
    owned_local_trial,
    r5_case,
    r6_delivery,
)

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]


async def test_history_http_orders_final_release_against_source_revocation(native_impact, monkeypatch):  # noqa: F811
    fixture, c = native_impact, native_impact.owned
    outside_line = "R7_RACE_RESTRICTED"
    async with c.session() as db:
        db.add(ProductLine(code=outside_line, name="R7 race restricted source", factory_id=c.factory_id))
        await db.commit()
    created = await fixture.employee.post(fixture.base + "/tasks", json=fixture.request)
    assert created.status_code == 201
    task_url = f"{fixture.base}/tasks/{created.json()['taskId']}"
    completed = await fixture.employee.post(task_url + "/launch")
    assert completed.status_code == 200
    detail_url = f"{task_url}/results/{completed.json()['resultId']}"
    detail = await fixture.employee.get(detail_url)
    assert detail.status_code == 200
    source, = [entry["id"] for measure in detail.json()["measures"] for entry in measure["evidence"]
        if entry["label"] == "PFMEA v1.0 · control-a"]
    evidence_url = f"{detail_url}/sources/{source}"
    assert c.fmea_id != fixture.fmea_id

    created = await fixture.employee.post(fixture.base + "/tasks", json=fixture.request | {
        "request_key": "r7-concurrent-history-reader",
    })
    assert created.status_code == 201, created.text
    launch_url = f"{fixture.base}/tasks/{created.json()['taskId']}/launch"
    fenced, proceed = asyncio.Event(), asyncio.Event()
    original_payload = history._review_payload

    async def hold_historical_reader(*args, **kwargs):
        fenced.set()
        await proceed.wait()
        return await original_payload(*args, **kwargs)

    with monkeypatch.context() as mp:
        mp.setattr(history, "_review_payload", hold_historical_reader)
        pending = asyncio.create_task(fixture.employee.get(detail_url))
        try:
            await asyncio.wait_for(fenced.wait(), 10)
            response = await asyncio.wait_for(fixture.employee.post(launch_url), 35)
        finally:
            proceed.set()
            assert (await asyncio.wait_for(pending, 10)).status_code == 200
    assert response.status_code == 200 and response.json()["status"] == "completed", response.text


    async def change_source_scope(line, started=None):
        async with c.session() as db:
            if started is not None:
                started.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
            await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id)
                .values(product_line_code=line))
            await db.commit()

    for url in (detail_url, evidence_url):
        # Pause the real request after its first full source authorization but
        # before it has taken any current employee or source rows.
        checked, proceed = asyncio.Event(), asyncio.Event()
        lock = history._lock_history

        async def wait_before_lock(*args, checked=checked, proceed=proceed, lock=lock):
            checked.set()
            await proceed.wait()
            await lock(*args)

        with monkeypatch.context() as mp:
            mp.setattr(history, "_lock_history", wait_before_lock)
            pending = asyncio.create_task(fixture.employee.get(url))
            try:
                await asyncio.wait_for(checked.wait(), 10)
                await asyncio.wait_for(change_source_scope(outside_line), 10)
            finally:
                proceed.set()
                result = await asyncio.wait_for(pending, 10)
        assert result.status_code == 404
        assert result.json() == {"detail": "Impact assessment unavailable"}
        assert source not in result.text and "control-a" not in result.text and "employee measure" not in result.text
        await change_source_scope(c.line)

        # In the reverse order, an already fenced reader wins. Observe the
        # blocked writer through PostgreSQL rather than relying on a delay.
        prepared = asyncio.get_running_loop().create_future()
        writer_pid = asyncio.get_running_loop().create_future()
        release = asyncio.Event()
        load_payload = history._review_payload

        async def wait_after_lock(db, *args, prepared=prepared, release=release, load_payload=load_payload, **kwargs):
            prepared.set_result(db)
            await release.wait()
            return await load_payload(db, *args, **kwargs)

        with monkeypatch.context() as mp:
            mp.setattr(history, "_review_payload", wait_after_lock)
            pending = asyncio.create_task(fixture.employee.get(url))
            writer = None
            try:
                reader_db = await asyncio.wait_for(prepared, 10)
                writer = asyncio.create_task(change_source_scope(outside_line, writer_pid))
                pid = await asyncio.wait_for(writer_pid, 10)
                blocked = text("SELECT pg_backend_pid() = ANY(pg_blocking_pids(:pid))")
                async with asyncio.timeout(10):
                    while not await reader_db.scalar(blocked, {"pid": pid}):
                        assert not writer.done(), "Source scope changed before the reader released its fence"
                        await asyncio.sleep(0.01)
            finally:
                release.set()
                result = await asyncio.wait_for(pending, 10)
                if writer is not None:
                    await asyncio.wait_for(writer, 10)
        assert result.status_code == 200
        assert "employee measure" in result.text or result.json()["text"] == "Verify program"
        assert (await fixture.employee.get(url)).status_code == 404
        async with c.session() as db:
            assert await db.scalar(select(FMEADocument.product_line_code).where(
                FMEADocument.fmea_id == c.fmea_id,
            )) == outside_line
        await change_source_scope(c.line)
