"""Internal R7 result publication within the caller's transaction."""

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_pfmea_impact import (
    AgentPfmeaImpactBinding, AgentPfmeaImpactReceipt, AgentPfmeaImpactResultReceipt,
)
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.schemas.pfmea_impact import ImpactSourceRef
from app.services.agent_runtime import pfmea_impact_tasks, task_updates
from app.services.agent_runtime.pfmea_impact_completion import (
    Analysis, Assessment, CompletionError, Conclusion, EvidenceVerifier, MeasureKey, NodeAdjustment,
    validate_completion,
)

RESULT_CONTRACT = "pfmea_impact_result.v1"
_MAX_ITEMS = 32
_MAX_RECEIPTS = 64
_MAX_RESULT_BYTES = 256 * 1024
_MAX_TEXT_BYTES = 16 * 1024
_MAX_REFERENCES = 256


class ImpactPublicationDenied(PermissionError):
    """The operation is not currently authorized for the bound task and run."""


class ImpactResultConflict(ValueError):
    """The requested operation does not match the immutable result."""


@dataclass(frozen=True, slots=True)
class PublicationScope:
    """Coordinates resolved from a trusted runtime credential, never the submission."""

    task_id: UUID
    run_id: UUID
    installation_id: UUID
    lease_epoch: int
    binding_digest: str


@dataclass(frozen=True, slots=True)
class ImpactResultSubmission:
    operation_key: str
    analyses: tuple[Analysis, ...]
    assessments: tuple[Assessment, ...]


@dataclass(frozen=True, slots=True)
class PublicationContext:
    scope: PublicationScope
    task: AgentTask
    run: AgentRun
    installation: AgentPluginInstallation
    binding: pfmea_impact_tasks.ImpactTaskBinding
    receipts: tuple[AgentPfmeaImpactReceipt, ...]
    sources: frozenset[ImpactSourceRef]
    replay: bool


@dataclass(frozen=True, slots=True)
class PublicationAuthorization:
    expected_measures: tuple[MeasureKey, ...]
    verifier: EvidenceVerifier


PublicationFence = Callable[[AsyncSession, PublicationContext], Awaitable[PublicationAuthorization]]


def _is_text(value: object) -> bool:
    if type(value) is not str or "\x00" in value or len(value) > _MAX_TEXT_BYTES:
        return False
    try:
        return len(value.encode("utf-8")) <= _MAX_TEXT_BYTES
    except UnicodeEncodeError:
        return False


def _is_text_list(value: object) -> bool:
    return type(value) is tuple and len(value) <= _MAX_REFERENCES and all(map(_is_text, value))


def _valid_assessment(item: object) -> bool:
    return (
        type(item) is Assessment
        and isinstance(item.measure_id, UUID)
        and (item.formal_revision is None or isinstance(item.formal_revision, UUID))
        and isinstance(item.conclusion, Conclusion)
        and _is_text(item.analysis_ref)
        and all(_is_text_list(refs) for refs in (
            item.evidence_refs, item.coverage_refs, item.exclusion_refs, item.missing_information,
        ))
        and type(item.node_adjustments) is tuple
        and len(item.node_adjustments) <= _MAX_REFERENCES
        and all(
            type(adjustment) is NodeAdjustment
            and _is_text(adjustment.target_ref) and _is_text(adjustment.proposal)
            for adjustment in item.node_adjustments
        )
    )


def _submission_payload(submission: ImpactResultSubmission) -> tuple[dict, str]:
    """Serialize only the typed proposal; it provides no authoritative metadata."""
    if (
        type(submission) is not ImpactResultSubmission
        or not _is_text(submission.operation_key)
        or not submission.operation_key.strip()
        or len(submission.operation_key) > 100
        or type(submission.analyses) is not tuple
        or type(submission.assessments) is not tuple
        or not 1 <= len(submission.analyses) <= _MAX_ITEMS
        or not 1 <= len(submission.assessments) <= _MAX_ITEMS
        or any(
            type(item) is not Analysis
            or not all(map(_is_text, (item.analysis_ref, item.reason, item.inference)))
            or not _is_text_list(item.fact_refs)
            for item in submission.analyses
        )
        or not all(map(_valid_assessment, submission.assessments))
    ):
        raise CompletionError("Invalid impact submission")

    def encode(value):
        if isinstance(value, UUID):
            return str(value)
        raise TypeError("Unsupported proposal value")

    try:
        raw = json.dumps(
            asdict(submission), default=encode, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CompletionError("Invalid impact submission") from exc
    if len(raw) > _MAX_RESULT_BYTES:
        raise CompletionError("Impact submission exceeds its size limit")
    return json.loads(raw), sha256(raw).hexdigest()


async def _lock_publication(db: AsyncSession, scope: PublicationScope):
    # Re-read after waits in the established mutation order.
    installation = await db.scalar(select(AgentPluginInstallation).where(
        AgentPluginInstallation.installation_id == scope.installation_id,
    ).with_for_update().execution_options(populate_existing=True))
    task = await db.scalar(select(AgentTask).where(
        AgentTask.task_id == scope.task_id,
    ).with_for_update().execution_options(populate_existing=True))
    run = await db.scalar(select(AgentRun).where(
        AgentRun.run_id == scope.run_id,
    ).with_for_update().execution_options(populate_existing=True))
    if (
        installation is None or task is None or run is None or not installation.enabled
        or installation.installation_id != scope.installation_id
        or task.task_id != scope.task_id or run.run_id != scope.run_id
        or not task.preferred_installation_id == run.installation_id == scope.installation_id
        or run.task_id != scope.task_id or run.plugin_version != installation.plugin_version
    ):
        raise ImpactPublicationDenied("Impact run unavailable")
    binding = await db.scalar(select(AgentPfmeaImpactBinding).where(
        AgentPfmeaImpactBinding.task_id == scope.task_id,
    ).execution_options(populate_existing=True))
    if (
        binding is None or binding.task_id != scope.task_id or binding.binding_digest != scope.binding_digest
        or not binding.actor_id == task.executor_user_id == task.initiator_id
    ):
        raise ImpactPublicationDenied("Impact binding unavailable")
    try:
        authenticated = await pfmea_impact_tasks.load_binding(db, scope.task_id)
    except pfmea_impact_tasks.ImpactTaskUnavailable as exc:
        raise ImpactPublicationDenied("Impact binding unavailable") from exc
    if (
        authenticated.activation.installation_id != installation.installation_id
        or authenticated.activation.plugin_version != installation.plugin_version
        or authenticated.activation.credential_epoch != installation.credential_epoch
    ):
        raise ImpactPublicationDenied("Impact binding unavailable")
    return installation, task, run, authenticated


def _is_exact_terminal(task: AgentTask, run: AgentRun, scope: PublicationScope) -> bool:
    return (
        task.status == run.status == "completed" and run.lease_epoch == scope.lease_epoch + 1
        and run.lease_expires_at is None and run.claim_key is None
    )


def _is_active(task: AgentTask, run: AgentRun, scope: PublicationScope) -> bool:
    return (
        task.status == "ready" and run.status == "active" and run.lease_epoch == scope.lease_epoch
        and run.lease_expires_at is not None and run.lease_expires_at > datetime.now(UTC)
    )


async def _publication_evidence(
    db: AsyncSession, scope: PublicationScope, binding: pfmea_impact_tasks.ImpactTaskBinding,
) -> tuple[tuple[AgentPfmeaImpactReceipt, ...], frozenset[ImpactSourceRef]]:
    receipt = AgentPfmeaImpactReceipt
    rows = tuple((await db.scalars(select(receipt).where(
        receipt.task_id == scope.task_id, receipt.run_id == scope.run_id, receipt.lease_epoch == scope.lease_epoch,
    ).order_by(receipt.receipt_id).limit(_MAX_RECEIPTS + 1))).all())
    if not rows or len(rows) > _MAX_RECEIPTS:
        raise ImpactPublicationDenied("Impact release evidence unavailable")
    sources = set()
    bound_capa_sources = frozenset(binding.capa.sources)
    if not bound_capa_sources:
        raise ImpactPublicationDenied("Formal CAPA projection unavailable")
    has_capa = False
    for row in rows:
        if (
            (row.task_id, row.run_id, row.lease_epoch) != (scope.task_id, scope.run_id, scope.lease_epoch)
            or not isinstance(row.payload, dict)
        ):
            raise ImpactPublicationDenied("Impact release evidence unavailable")
        if row.kind == "release":
            module, refs = row.payload.get("module"), row.payload.get("sources")
            if (
                module not in ("capa", "fmea") or row.payload.get("binding_digest") != scope.binding_digest
                or not isinstance(refs, list) or not 1 <= len(refs) <= 256
            ):
                raise ImpactPublicationDenied("Impact release evidence unavailable")
            try:
                projection_sources = frozenset(ImpactSourceRef.model_validate(ref) for ref in refs)
            except ValidationError as exc:
                raise ImpactPublicationDenied("Impact release evidence unavailable") from exc
            if module == "capa":
                if not bound_capa_sources <= projection_sources:
                    raise ImpactPublicationDenied("Formal CAPA projection unavailable")
                has_capa = True
            sources.update(projection_sources)
        elif row.kind == "coverage":
            if row.payload.get("binding_digest") != scope.binding_digest:
                raise ImpactPublicationDenied("Impact coverage unavailable")
        elif row.kind != "page_confirmation":
            raise ImpactPublicationDenied("Impact release evidence unavailable")
    if not has_capa:
        raise ImpactPublicationDenied("Formal CAPA projection unavailable")
    return rows, frozenset(sources)


async def publish_pfmea_impact_result(
    db: AsyncSession,
    scope: PublicationScope,
    submission: ImpactResultSubmission,
    *,
    authorize: PublicationFence,
) -> UUID:
    """Prepare one result and a terminal transition for the caller to commit.

    The caller authenticates the signed run (including a dedicated terminal
    replay path) and binds the tenant before entry. The mandatory fence locks
    and rechecks current installation, grants, actor, frozen versions and all
    supplied source references. It supplies a verifier based on server evidence
    only. Neither the initial authentication nor these row locks replaces it.
    """
    payload, request_digest = _submission_payload(submission)
    with db.no_autoflush:
        installation, task, run, binding = await _lock_publication(db, scope)
        replay = _is_exact_terminal(task, run, scope)
        if not replay and not _is_active(task, run, scope):
            raise ImpactPublicationDenied("Impact run unavailable")
        rows, sources = await _publication_evidence(db, scope, binding)
        receipt_ids = {row.receipt_id for row in rows}
        existing = tuple((await db.scalars(select(AgentResult).where(
            AgentResult.task_id == scope.task_id, AgentResult.run_id == scope.run_id,
        ).limit(2).execution_options(populate_existing=True))).all())
        links = set()
        if len(existing) == 1:
            links = {row.receipt_id for row in (await db.scalars(select(
                AgentPfmeaImpactResultReceipt,
            ).where(AgentPfmeaImpactResultReceipt.result_id == existing[0].result_id))).all()}

        permit = await authorize(db, PublicationContext(
            scope, task, run, installation, binding, rows, sources, replay,
        ))
        expected_measures = tuple((item.measure_id, item.formal_revision) for item in binding.capa.measures)
        if (
            not isinstance(permit, PublicationAuthorization)
            or len(permit.expected_measures) != len(expected_measures)
            or set(permit.expected_measures) != set(expected_measures)
        ):
            raise ImpactPublicationDenied("Impact publication unavailable")

    if replay:
        if not _is_exact_terminal(task, run, scope) or len(existing) != 1:
            raise ImpactPublicationDenied("Impact result unavailable")
        prior = existing[0]
        if (
            prior.task_id != scope.task_id or prior.run_id != scope.run_id or prior.data_class != "restricted"
            or not isinstance(prior.payload, dict) or prior.payload.get("contract") != RESULT_CONTRACT
            or prior.payload.get("binding_digest") != scope.binding_digest
            or prior.payload.get("lease_epoch") != scope.lease_epoch or links != receipt_ids
        ):
            raise ImpactPublicationDenied("Impact result unavailable")
        if prior.idempotency_key != submission.operation_key or prior.payload.get("request_digest") != request_digest:
            raise ImpactResultConflict("Impact operation does not match the completed result")
        return prior.result_id

    if not _is_active(task, run, scope):
        raise ImpactPublicationDenied("Impact run unavailable")
    if existing:
        raise ImpactResultConflict("Impact run already has a result")
    conclusion = validate_completion(
        expected_measures, submission.analyses, submission.assessments, verifier=permit.verifier,
    )
    if not _is_active(task, run, scope):
        raise ImpactPublicationDenied("Impact run unavailable")

    # A failure after the first flush must not leave a result that a caller could
    # accidentally commit without associations, activity or the terminal state.
    result_id = uuid4()
    result = AgentResult(
        result_id=result_id, task_id=scope.task_id, run_id=scope.run_id,
        idempotency_key=submission.operation_key, data_class="restricted", payload={
            "contract": RESULT_CONTRACT, "binding_digest": scope.binding_digest, "lease_epoch": scope.lease_epoch,
            "request_digest": request_digest, "conclusion": conclusion.value,
            "analyses": payload["analyses"], "assessments": payload["assessments"],
        },
    )
    async with db.begin_nested():
        db.add(result)
        await db.flush()
        db.add_all(AgentPfmeaImpactResultReceipt(result_id=result_id, receipt_id=receipt_id)
                   for receipt_id in sorted(receipt_ids))
        task.status = run.status = "completed"
        run.lease_epoch += 1
        run.lease_expires_at = None
        run.claim_key = None
        db.add(AuditLog(
            table_name="agent_results", record_id=result_id, action="COMPLETE_AGENT_PFMEA_IMPACT",
            operated_by=task.executor_user_id, factory_id=task.factory_id, correlation_id=run.run_id,
            changed_fields={"task_id": str(task.task_id), "run_id": str(run.run_id), "status": "completed"},
        ))
        await task_updates.append_update(db, task_id=task.task_id, kind="result", object_id=result_id)
        await db.flush()
    return result_id
