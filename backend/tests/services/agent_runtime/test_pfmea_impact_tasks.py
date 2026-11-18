"""R7 task admission stays separate from the existing runtime profiles."""
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_unreleased_r7_profile_rejects_before_preflight_or_writes():
    from app.services.agent_runtime.pfmea_impact_tasks import (
        ImpactTaskRequest, ImpactTaskUnavailable, create_task,
    )

    class NoBusinessAccess:
        def __getattr__(self, name):
            pytest.fail(f"disabled profile touched {name}")

    request = ImpactTaskRequest(report_id=uuid4(), fmea_id=uuid4(), approved_version_id=uuid4(),
        installation_id=uuid4(), model_deployment_id=uuid4(), request_key="default-deny")
    scope = SimpleNamespace(user=SimpleNamespace(user_id=uuid4()))
    with pytest.raises(ImpactTaskUnavailable, match="^PFMEA impact task unavailable$"):
        await create_task(NoBusinessAccess(), scope, request)


def test_task_input_cannot_choose_permission_or_claim_server_binding():
    from pydantic import ValidationError
    from app.services.agent_runtime.pfmea_impact_tasks import ImpactTaskRequest

    request = dict(report_id=uuid4(), fmea_id=uuid4(), approved_version_id=uuid4(),
        installation_id=uuid4(), model_deployment_id=uuid4(), request_key="server-owned")
    for protected in ("capa_binding", "source_refs", "scope_generation", "executor_user_id", "profile"):
        with pytest.raises(ValidationError):
            ImpactTaskRequest.model_validate({**request, protected: "untrusted"})


import pytest_asyncio
from sqlalchemy import func, select, update

from tests.capa.test_capa_impact_material import (  # noqa: F401
    adopted_case, d4_text_local_trial, owned_local_trial, r5_case, r6_delivery,
)


@pytest_asyncio.fixture
async def impact_case(adopted_case, monkeypatch):
    from app.models.agent_model_deployment import AgentModelDeployment
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.fmea import FMEADocument
    from app.services.agent_runtime import model_egress, pfmea_impact_tasks as tasks
    from app.services.version_service import _create_fmea_version_no_commit

    c = adopted_case
    plugin_id, model_id = uuid4(), uuid4()
    async with c.session() as db:
        # The production controlled R7 profile remains disabled. This fixture
        # supplies pins only for exercising the admission transaction.
        db.add(AgentPluginInstallation(installation_id=plugin_id, plugin_key=tasks.R7_PLUGIN_KEY,
            plugin_version="1.0.0", manifest={}, secret_hash="synthetic", enabled=True, created_by=c.user_id))
        model = AgentModelDeployment(deployment_id=model_id, name="R7 synthetic deployment", version="1.0.0",
            tenant_generation=c.binding.generation, kind="local", provider="openai", model="synthetic",
            base_url="http://127.0.0.1:18080", allowed_addresses=["127.0.0.1"], credential_ref="synthetic",
            api_protocol="chat_completions", executor_pins={"profile": tasks.R7_PROFILE},
            created_by=c.user_id, enabled=True)
        model.config_hmac = model_egress._digest(db, model)
        db.add(model)
        docs, approved = [], []
        for kind, line in (("PFMEA", c.line), ("PFMEA", c.line), ("DFMEA", c.line), ("PFMEA", "OTHER")):
            doc = FMEADocument(document_no=f"R7-{uuid4().hex[:8]}", title=f"Target {kind} {line}",
                fmea_type=kind, factory_id=c.factory_id, product_line_code=line,
                status="in_review", graph_data={"nodes": [], "edges": []}, created_by=c.user_id)
            db.add(doc)
            await db.flush()
            docs.append(doc.fmea_id)
            version = await _create_fmea_version_no_commit(db, doc, "approve", None, c.user_id)
            approved.append(version.version_id)
            if len(docs) == 1:
                current_submit = await _create_fmea_version_no_commit(db, doc, "submit", None, c.user_id)
                c.r7_submit_id = current_submit.version_id
        await db.commit()
    activation = tasks.ImpactActivation(profile=tasks.R7_PROFILE, installation_id=plugin_id,
        plugin_version="1.0.0", credential_epoch=0, deployment_id=model_id,
        deployment_version=model.version, deployment_config_hmac=model.config_hmac)

    async def controlled_activation(db, scope, request):
        if request.model_deployment_id == c.model_id:
            # Even an incorrectly forwarded legacy model must fail the pins
            # independently checked by the admission transaction.
            legacy = await db.get(AgentModelDeployment, c.model_id)
            return activation.model_copy(update={"deployment_id": c.model_id, "deployment_version": legacy.version,
                "deployment_config_hmac": legacy.config_hmac})
        return activation

    monkeypatch.setattr(tasks, "_controlled_activation", controlled_activation)
    c.r7_docs, c.r7_approvals = docs, approved
    c.r7_request = tasks.ImpactTaskRequest(report_id=c.report_id, fmea_id=docs[0], approved_version_id=approved[0],
        installation_id=plugin_id, model_deployment_id=model_id, request_key="r7-admission")
    return c


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_picker_projects_only_approved_visible_metadata(impact_case):
    from app.services.agent_runtime import pfmea_impact_tasks as tasks
    from tests.capa.test_d4_source_access import SQLSpy

    c = impact_case
    async with c.session() as db:
        with SQLSpy(await db.connection()) as spy:
            first = await tasks.list_targets(db, c.impact_scope, c.report_id, page_size=1)
            second = await tasks.list_targets(db, c.impact_scope, c.report_id, page=2, page_size=1)
        assert first["total"] == second["total"] == 2
        options = first["items"] + second["items"]
        assert {item.fmea_id for item in options} == set(c.r7_docs[:2])
        assert {item.version_id for item in options} == set(c.r7_approvals[:2])
        assert next(item for item in options if item.fmea_id == c.r7_docs[0]).has_unapproved_revision
        assert not spy.node_reads
        assert not any("select fmea_versions.snapshot" in statement for statement in spy.statements)
        # A draft baseline, wrong module and wrong product line fail even when
        # sent straight to admission instead of chosen through the picker.
        for index, version_id in ((0, c.r7_submit_id), (2, c.r7_approvals[2]), (3, c.r7_approvals[3])):
            with pytest.raises(tasks.ImpactTaskUnavailable):
                await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
                    "fmea_id": c.r7_docs[index], "approved_version_id": version_id,
                }))
            await db.rollback()
        with pytest.raises(tasks.ImpactTaskUnavailable):
            await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
                "model_deployment_id": c.model_id,
            }))
        await db.rollback()
        with pytest.raises(tasks.ImpactTaskUnavailable):
            await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
                "request_key": c.create_body["request_key"],
            }))


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_concurrent_replay_reuses_atomic_immutable_binding_and_no_run(impact_case):
    import asyncio
    from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding
    from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant
    from app.models.audit import AuditLog
    from app.services.agent_runtime import pfmea_impact_tasks as tasks

    c = impact_case

    async def create():
        async with c.session() as db:
            return await tasks.create_task(db, c.impact_scope, c.r7_request)

    first, second = await asyncio.gather(create(), create())
    assert first.task_id == second.task_id
    assert {first.replayed, second.replayed} == {False, True}
    async with c.session() as db:
        task = await db.get(AgentTask, first.task_id)
        binding = await tasks.load_binding(db, first.task_id)
        assert task.status == "blocked_capability"
        assert set(item.measure_id for item in binding.capa.measures) == set(c.impact_measure_ids)
        assert binding.target.approved_version_id == c.r7_approvals[0]
        assert binding.target.minor_no == 0
        assert await db.scalar(select(func.count()).select_from(AgentPfmeaImpactBinding)) == 1
        assert await db.scalar(select(func.count()).where(AgentRun.task_id == task.task_id)) == 0
        assert await db.scalar(select(func.count()).where(AgentTaskGrant.task_id == task.task_id)) == 0
        assert await db.scalar(select(func.count()).where(AuditLog.record_id == task.task_id,
            AuditLog.action == "CREATE_PFMEA_IMPACT_TASK")) == 1
        row = await db.get(AgentPfmeaImpactBinding, first.task_id)
        assert "employee measure" not in str(row.binding)
        with pytest.raises(tasks.ImpactTaskConflict):
            await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
                "fmea_id": c.r7_docs[1], "approved_version_id": c.r7_approvals[1],
            }))


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["D6_VERIFICATION", "D8_CLOSURE", "ARCHIVED"])
async def test_terminal_or_late_report_can_bind_without_mutating_business_state(impact_case, stage):
    from app.models.capa import CAPAEightD
    from app.services.agent_runtime import pfmea_impact_tasks as tasks

    c = impact_case
    async with c.session() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id).values(status=stage))
        await db.commit()
    async with c.session() as db:
        receipt = await tasks.create_task(db, c.impact_scope, c.r7_request)
        assert not receipt.replayed
        report = await db.get(CAPAEightD, c.report_id)
        assert report.status == stage


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_replay_denies_revoked_source_and_untrusted_previous_result(impact_case):
    from app.models.role import RolePermission
    from app.models.user import User
    from app.services.agent_runtime import pfmea_impact_tasks as tasks

    c = impact_case
    async with c.session() as db:
        with pytest.raises(tasks.ImpactTaskUnavailable):
            await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
                "request_key": "reassess", "previous_result_id": uuid4(),
            }))
        await db.rollback()
        receipt = await tasks.create_task(db, c.impact_scope, c.r7_request)
        assert not receipt.replayed
        role_id = await db.scalar(select(User.role_id).where(User.user_id == c.user_id))
        await db.execute(update(RolePermission).where(RolePermission.role_id == role_id,
            RolePermission.module == "fmea").values(permission_level=0))
        await db.commit()
    async with c.session() as db:
        with pytest.raises(tasks.ImpactTaskUnavailable):
            await tasks.create_task(db, c.impact_scope, c.r7_request)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_scope_aba_invalidates_old_approval_and_old_task_binding(impact_case):
    from app.models.fmea import FMEADocument
    from app.services.agent_runtime import pfmea_impact_tasks as tasks
    from app.services.version_service import _create_fmea_version_no_commit

    c = impact_case
    async with c.session() as db:
        receipt = await tasks.create_task(db, c.impact_scope, c.r7_request)
        old = await tasks.load_binding(db, receipt.task_id)
        doc = await db.get(FMEADocument, c.r7_docs[0])
        doc.product_line_code = "OTHER"
        await db.flush()
        doc.product_line_code = c.line
        await db.commit()
    async with c.session() as db:
        assert c.r7_docs[0] not in {item.fmea_id for item in
            (await tasks.list_targets(db, c.impact_scope, c.report_id))["items"]}
        with pytest.raises(tasks.ImpactTaskUnavailable):
            await tasks.create_task(db, c.impact_scope, c.r7_request)
        await db.rollback()
        doc = await db.get(FMEADocument, c.r7_docs[0])
        approved = await _create_fmea_version_no_commit(db, doc, "approve", None, c.user_id)
        new_version = approved.version_id
        await db.commit()
        with pytest.raises(tasks.ImpactTaskUnavailable):
            await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
                "approved_version_id": new_version,
            }))
        await db.rollback()
        fresh = await tasks.create_task(db, c.impact_scope, c.r7_request.model_copy(update={
            "approved_version_id": new_version, "request_key": "scope-reassessment",
        }))
        new = await tasks.load_binding(db, fresh.task_id)
        assert old.target.scope_generation != new.target.scope_generation
