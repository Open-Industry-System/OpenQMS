"""Internal R7 publication contract tested without external authorities or a DB."""
from contextlib import asynccontextmanager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.agent_pfmea_impact import (
    AgentPfmeaImpactBinding, AgentPfmeaImpactReceipt, AgentPfmeaImpactResultReceipt,
)
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.schemas.pfmea_impact import ImpactSourceRef
from app.services.agent_runtime import pfmea_impact_tasks, task_updates
from app.services.agent_runtime.pfmea_impact_completion import Analysis, Assessment, Conclusion
from app.services.agent_runtime.pfmea_impact_results import (
    ImpactPublicationDenied,
    ImpactResultConflict,
    ImpactResultSubmission,
    PublicationAuthorization,
    PublicationScope,
    publish_pfmea_impact_result,
)

TASK, RUN, INSTALLATION, ACTOR, FACTORY, REPORT, MEASURE = (UUID(int=i) for i in range(1, 8))
BINDING_DIGEST = "b" * 64
SCOPE = PublicationScope(TASK, RUN, INSTALLATION, 7, BINDING_DIGEST)
REQUEST = ImpactResultSubmission(
    "retry-key",
    (Analysis("analysis", "Sensitive original analysis."),),
    (Assessment(MEASURE, None, "analysis", Conclusion.INSUFFICIENT_EVIDENCE,
                missing_information=("The qualified sample was not inspected.",)),),
)


class Verifier:
    def verify_evidence(self, measure, refs):
        return False

    def verify_impact_path(self, measure, target_ref, evidence_refs):
        return False

    def verify_coverage(self, measure, refs):
        return False

    def verify_exclusion(self, measure, refs, coverage_refs):
        return False


class _Scalars(list):
    def all(self):
        return self


class Session:
    no_autoflush = nullcontext()

    def __init__(self):
        self.task = SimpleNamespace(task_id=TASK, target_capa_id=REPORT, status="ready",
                                    executor_user_id=ACTOR, initiator_id=ACTOR, factory_id=FACTORY,
                                    preferred_installation_id=INSTALLATION)
        self.run = SimpleNamespace(run_id=RUN, task_id=TASK, installation_id=INSTALLATION,
                                   plugin_version="1", status="active", lease_epoch=7,
                                   lease_expires_at=datetime.now(UTC) + timedelta(minutes=10),
                                   claim_key="claim")
        self.installation = SimpleNamespace(
            installation_id=INSTALLATION, enabled=True, plugin_version="1", credential_epoch=0,
        )
        self.bound_measures = (SimpleNamespace(measure_id=MEASURE, formal_revision=None),)
        self.binding = SimpleNamespace(task_id=TASK, actor_id=ACTOR, binding_digest=BINDING_DIGEST, binding={})
        self.receipts = [self.release(20, "capa"), self.release(21, "fmea")]
        self.bound_sources = (ImpactSourceRef.model_validate(self.receipts[0].payload["sources"][0]),)
        self.writes = []
        self.lookups = []
        self.updates = []
        self.fail_activity = False

    def release(self, receipt_id, module):
        return SimpleNamespace(receipt_id=UUID(int=receipt_id), task_id=TASK, run_id=RUN,
                               lease_epoch=7, kind="release", scope_digest="c" * 64,
                               page_key=None, payload={
                                   "module": module, "binding_digest": BINDING_DIGEST,
                                   "sources": [{
                                       "source_id": str(UUID(int=receipt_id + 10)), "module": module,
                                       "object_id": str(REPORT), "factory_id": str(FACTORY),
                                       "product_line_code": "R7", "projection_id": f"{module}.read",
                                       "version": "1",
                                   }],
                               })

    async def scalar(self, query):
        entity = query.column_descriptions[0]["entity"]
        self.lookups.append(entity)
        return {
            AgentTask: self.task, AgentRun: self.run,
            AgentPluginInstallation: self.installation, AgentPfmeaImpactBinding: self.binding,
        }[entity]

    async def scalars(self, query):
        entity = query.column_descriptions[0]["entity"]
        self.lookups.append(entity)
        if entity == AgentPfmeaImpactReceipt:
            return _Scalars(self.receipts)
        return _Scalars([row for row in self.writes if isinstance(row, entity)])

    async def flush(self):
        pass

    def add(self, row):
        self.writes.append(row)

    def add_all(self, rows):
        self.writes.extend(rows)

    @asynccontextmanager
    async def begin_nested(self):
        before = len(self.writes), vars(self.task).copy(), vars(self.run).copy()
        try:
            yield
        except BaseException:
            length, task, run = before
            del self.writes[length:]
            vars(self.task).update(task)
            vars(self.run).update(run)
            raise


@pytest.fixture
def db(monkeypatch):
    session = Session()

    async def append_update(db, *, task_id, kind, object_id):
        if db.fail_activity:
            raise RuntimeError("activity unavailable")
        db.updates.append((task_id, kind, object_id))

    async def load_binding(db, task_id):
        assert task_id == TASK
        return SimpleNamespace(
            activation=SimpleNamespace(installation_id=INSTALLATION, plugin_version="1", credential_epoch=0),
            capa=SimpleNamespace(measures=db.bound_measures, sources=db.bound_sources),
        )

    monkeypatch.setattr(task_updates, "append_update", append_update)
    monkeypatch.setattr(pfmea_impact_tasks, "load_binding", load_binding)
    return session


async def authorize(db, context):
    assert context.scope == SCOPE
    assert {row.receipt_id for row in context.receipts} == {UUID(int=20), UUID(int=21)}
    assert db.task.status == ("completed" if context.replay else "ready")
    return PublicationAuthorization(((MEASURE, None),), Verifier())


@pytest.mark.asyncio
async def test_publication_links_every_possible_release_and_finishes_in_one_transaction(db):
    result_id = await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize)

    assert db.lookups[:3] == [AgentPluginInstallation, AgentTask, AgentRun]
    result, = [row for row in db.writes if isinstance(row, AgentResult)]
    assert result.result_id == result_id
    assert result.payload["conclusion"] == "insufficient_evidence"
    links = [row for row in db.writes if isinstance(row, AgentPfmeaImpactResultReceipt)]
    assert {(row.result_id, row.receipt_id) for row in links} == {
        (result_id, UUID(int=20)), (result_id, UUID(int=21)),
    }
    assert db.task.status == db.run.status == "completed"
    assert db.run.lease_epoch == 8
    assert db.run.lease_expires_at is None
    assert db.run.claim_key is None
    assert db.updates == [(TASK, "result", result_id)]
    audit, = [row for row in db.writes if isinstance(row, AuditLog)]
    assert "Sensitive original analysis" not in repr(audit.changed_fields)
    assert "qualified sample" not in repr(audit.changed_fields)


@pytest.mark.asyncio
async def test_exact_completed_replay_rechecks_access_and_never_mutates_state(db):
    first = await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize)
    writes = db.writes.copy()

    assert await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize) == first
    assert db.writes == writes
    for changed in (replace(REQUEST, operation_key="other-key"),
                    replace(REQUEST, analyses=(Analysis("analysis", "Different."),))):
        with pytest.raises(ImpactResultConflict):
            await publish_pfmea_impact_result(db, SCOPE, changed, authorize=authorize)
    assert db.writes == writes
    assert db.updates == [(TASK, "result", first)]

    async def revoked(db, context):
        assert context.replay
        raise ImpactPublicationDenied("Access withdrawn")

    with pytest.raises(ImpactPublicationDenied):
        await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=revoked)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["cancelled", "expired", "stale-epoch", "wrong-binding"])
async def test_noncurrent_run_cannot_publish(db, state):
    scope = SCOPE
    if state == "cancelled":
        db.task.status, db.run.status = "cancelled", "stopped"
    elif state == "expired":
        db.run.lease_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    elif state == "stale-epoch":
        scope = replace(SCOPE, lease_epoch=6)
    else:
        scope = replace(SCOPE, binding_digest="0" * 64)
    with pytest.raises(ImpactPublicationDenied):
        await publish_pfmea_impact_result(db, scope, REQUEST, authorize=authorize)
    assert not db.writes


@pytest.mark.asyncio
async def test_final_fence_can_reject_all_releases_before_any_write(db):
    async def denied(db, context):
        assert not context.replay
        assert len(context.receipts) == 2
        raise ImpactPublicationDenied("Source permission changed")

    with pytest.raises(ImpactPublicationDenied):
        await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=denied)

    assert not db.writes
    assert db.task.status == "ready" and db.run.status == "active"


@pytest.mark.asyncio
async def test_rejects_binding_with_no_formal_capa_projection_release(db):
    db.receipts.pop(0)
    with pytest.raises(ImpactPublicationDenied):
        await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize)
    assert not db.writes


@pytest.mark.asyncio
async def test_result_and_finished_state_cannot_survive_failed_activity_write(db):
    db.fail_activity = True
    with pytest.raises(RuntimeError, match="activity unavailable"):
        await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize)

    assert not db.writes
    assert db.task.status == "ready" and db.run.status == "active"
    assert db.run.lease_epoch == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [
    replace(REQUEST, analyses=(Analysis("analysis", "Reason", inference={"source_labels": "untrusted"}),)),
    replace(REQUEST, assessments=(replace(REQUEST.assessments[0], missing_information=("gap\0",)),)),
    replace(REQUEST, assessments=(replace(REQUEST.assessments[0], conclusion="injected"),)),
])
async def test_raw_source_metadata_and_invalid_types_never_enter_publication(db, invalid):
    from app.services.agent_runtime.pfmea_impact_completion import CompletionError

    with pytest.raises(CompletionError):
        await publish_pfmea_impact_result(db, SCOPE, invalid, authorize=authorize)
    assert not db.lookups
    assert not db.writes


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True], ids=["concurrent-replay", "publication-rollback"])
async def test_result_terminal_transition_has_real_transaction_boundary(committed_runtime, monkeypatch, failure):
    import asyncio
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.agent_readonly_control import AgentTaskUpdate
    from app.services.agent_runtime.pfmea_impact_ledger import record_release
    from app.services.agent_runtime.pfmea_impact_release import PageScope

    c = committed_runtime
    async with c.factory(binding=c.binding) as session:
        task = await session.get(AgentTask, c.task_id)
        run = await session.get(AgentRun, c.run_id)
        plugin = await session.get(AgentPluginInstallation, c.plugin_id)
        target_id, version_id = uuid4(), uuid4()
        formal_source = ImpactSourceRef(
            source_id=uuid4(), module="capa", object_id=task.target_capa_id, projection_id="capa.test",
            version="1", factory_id=task.factory_id, product_line_code="R7",
        )
        binding = pfmea_impact_tasks.ImpactTaskBinding(
            capa={
                "tenant_id": c.binding.tenant_id, "tenant_generation": c.binding.generation,
                "report_id": task.target_capa_id, "factory_id": task.factory_id,
                "product_line_code": "R7", "root_revision": uuid4(), "proof_id": uuid4(),
                "verification_ref": uuid4(), "verification_version": "1",
                "measures": [{"measure_id": MEASURE, "formal_revision": None}], "sources": [formal_source],
            },
            target={
                "fmea_id": target_id, "approved_version_id": version_id, "major_no": 1,
                "snapshot_hash": "c" * 64, "scope_generation": uuid4(),
            },
            activation={
                "profile": pfmea_impact_tasks.R7_PROFILE, "installation_id": c.plugin_id,
                "plugin_version": plugin.plugin_version, "credential_epoch": plugin.credential_epoch,
                "deployment_id": uuid4(), "deployment_version": "1", "deployment_config_hmac": "a" * 64,
            },
            previous_result_id=None,
        ).model_dump(mode="json")
        digest = pfmea_impact_tasks._stamp(task.task_id, c.user_id, task.request_key, binding)
        scope = PublicationScope(task.task_id, run.run_id, c.plugin_id, run.lease_epoch, digest)
        session.add(AgentPfmeaImpactBinding(
            task_id=task.task_id, actor_id=c.user_id, request_key=task.request_key,
            binding=binding, binding_digest=digest,
        ))
        await session.flush()
        ledger_scope = PageScope(
            scope.task_id, scope.run_id, scope.lease_epoch, scope.binding_digest, "c" * 64, "formal",
        )
        released = set()
        for module, object_id in (("capa", task.target_capa_id), ("fmea", target_id)):
            released.add(await record_release(
                session, ledger_scope, module=module, body=b"projection", element_keys=(),
                sources=(formal_source if module == "capa" else ImpactSourceRef(
                    source_id=uuid4(), module="fmea", object_id=object_id, projection_id="fmea.test",
                    version="1", factory_id=task.factory_id, product_line_code="R7",
                ),),
            ))
        await session.commit()

    replay_flags = []

    async def publication_fence(session, context):
        # Dedicated authorizer is not under test; both attempts must pass
        # the exact complete durable evidence set to it.
        assert {row.receipt_id for row in context.receipts} == released
        assert {source.module for source in context.sources} == {"capa", "fmea"}
        replay_flags.append(context.replay)
        return PublicationAuthorization(((MEASURE, None),), Verifier())

    async def publish():
        async with c.factory(binding=c.binding) as session:
            result_id = await publish_pfmea_impact_result(session, scope, REQUEST, authorize=publication_fence)
            await session.commit()
            return result_id

    if failure:
        async def fail_after_staged_activity(session, **kwargs):
            await real_append(session, **kwargs)
            raise RuntimeError("after activity flush")

        real_append = task_updates.append_update
        monkeypatch.setattr(task_updates, "append_update", fail_after_staged_activity)
        async with c.factory(binding=c.binding) as session:
            with pytest.raises(RuntimeError, match="after activity flush"):
                await publish_pfmea_impact_result(session, scope, REQUEST, authorize=publication_fence)
            # Even if this caller handles the error, no partial publication can commit.
            await session.commit()
    else:
        first, second = await asyncio.wait_for(asyncio.gather(publish(), publish()), timeout=15)
        assert first == second
        assert replay_flags == [False, True]

    async with c.factory(binding=c.binding) as session:
        task = await session.get(AgentTask, c.task_id)
        run = await session.get(AgentRun, c.run_id)
        results = (await session.scalars(select(AgentResult).where(AgentResult.task_id == task.task_id))).all()
        updates = (await session.scalars(select(AgentTaskUpdate).where(
            AgentTaskUpdate.task_id == task.task_id, AgentTaskUpdate.kind == "result",
        ))).all()
        audits = (await session.scalars(select(AuditLog).where(
            AuditLog.correlation_id == run.run_id, AuditLog.action == "COMPLETE_AGENT_PFMEA_IMPACT",
        ))).all()
        if failure:
            assert not results and not updates and not audits
            assert task.status == "ready" and run.status == "active"
            assert run.lease_epoch == scope.lease_epoch
        else:
            result, = results
            links = (await session.scalars(select(AgentPfmeaImpactResultReceipt).where(
                AgentPfmeaImpactResultReceipt.result_id == result.result_id,
            ))).all()
            assert {row.receipt_id for row in links} == released
            assert result.result_id == first == updates[0].object_id == audits[0].record_id
            assert len(updates) == len(audits) == 1
            assert task.status == run.status == "completed"
            assert run.lease_epoch == scope.lease_epoch + 1 and run.lease_expires_at is None


@pytest.mark.asyncio
async def test_current_allow_decision_cannot_replace_the_stored_measure_set(db):
    db.bound_measures = (SimpleNamespace(measure_id=MEASURE, formal_revision=None),
                         SimpleNamespace(measure_id=UUID(int=122), formal_revision=None))
    with pytest.raises(ImpactPublicationDenied):
        await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize)
    assert not db.writes


@pytest.mark.asyncio
async def test_projection_evidence_must_cover_every_source_of_signed_capa_material(db):
    db.bound_sources = (ImpactSourceRef.model_validate({
        **db.receipts[0].payload["sources"][0], "source_id": str(UUID(int=110)),
    }),)
    with pytest.raises(ImpactPublicationDenied):
        await publish_pfmea_impact_result(db, SCOPE, REQUEST, authorize=authorize)
    assert not db.writes
