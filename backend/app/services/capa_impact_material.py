"""Resolve the formal CAPA inputs and their complete original source authority.

This service prepares business-owned material. The runtime owns final release,
recipient authorization, and the database locks that serialize that release.
"""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select

from app.models.agent_d5_basis import AgentD5BasisReceipt, AgentD5CommandBasis
from app.models.agent_d5_command import AgentD5Command
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal
from app.models.capa_r6 import (
    CapaD5MeasureRevision,
    CapaR6ReportSnapshot,
    CapaR6RootDeliveryBinding,
    CapaR6RootRevisionBody,
    CapaR6RootRevisionSource,
    CapaR6SourceOrigin,
)
from app.schemas.pfmea_impact import (
    CapaImpactBinding, CapaImpactMaterial, CapaImpactMeasure, ImpactSourceRef, MeasureKey,
)
from app.services import capa_d4_material, capa_d5_measures, capa_r6_delivery
from app.services.capa_current_access import current_capa_access, current_capa_target_metadata
from app.services.capa_d5_corrections import current_measure
from app.services.capa_legacy_capture import require_ordinary_capture_material
from app.services.capa_verification_sources import authorize_verifications
from app.state_machines.eightd_state import EightDState

CAPA_IMPACT_MATERIAL_CAPABILITY = "capa.pfmea_impact.material.v1"
_MAX_MEASURES = 32
_MAX_SOURCES = 128
_MAX_FIELD_BYTES = 16 * 1024
_MAX_MATERIAL_BYTES = 256 * 1024
_EARLY_STAGES = {
    EightDState.D1_TEAM, EightDState.D2_DESCRIPTION, EightDState.D3_INTERIM, EightDState.D4_ROOT_CAUSE,
}
_ASSESSABLE_STAGES = frozenset(EightDState) - _EARLY_STAGES


class ImpactMaterialUnavailable(PermissionError):
    def __init__(self):
        super().__init__("CAPA impact material unavailable")


class ImpactMaterialNotReady(ValueError):
    def __init__(self, reason: Literal["d4_not_verified", "d5_not_adopted", "sources_unavailable", "too_large"]):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class _MaterialMetadata:
    binding: CapaImpactBinding
    primary: ImpactSourceRef
    by_measure: dict[UUID, tuple[UUID, ...]]


async def _proof_and_revision(db, report_id, tenant_generation, history):
    proof_model = CapaD4RootCauseSourceProof
    query = select(proof_model).where(proof_model.report_id == report_id,
                                      proof_model.tenant_generation == tenant_generation)
    if history is None:
        query = query.where(proof_model.status == "active", proof_model.invalidated_at.is_(None))
    else:
        query = query.where(proof_model.proof_id == history.proof_id)
    candidates = (await db.scalars(query.limit(2).execution_options(populate_existing=True))).all()
    if not candidates and history is None:
        raise ImpactMaterialNotReady("d4_not_verified")
    if len(candidates) != 1:
        raise ImpactMaterialUnavailable()
    proof = candidates[0]
    revision = await db.get(CapaD4RootCauseRevision, proof.revision_id, populate_existing=True)
    if (revision is None or revision.report_id != report_id or revision.field_hmac != proof.field_hmac
            or proof.declaration_kind != "employee_declared_complete_v1"):
        raise ImpactMaterialUnavailable()
    return proof, revision


async def _revision_sources(db, scope, report_id, revision, proof):
    body = (await db.execute(select(
        CapaR6RootRevisionBody.source_count, CapaR6RootRevisionBody.origin_digest,
        CapaR6RootRevisionBody.binding_state,
    ).where(CapaR6RootRevisionBody.revision_id == revision.revision_id,
            CapaR6RootRevisionBody.report_id == report_id))).one_or_none()
    if body is None:
        raise ImpactMaterialNotReady("sources_unavailable")
    origin_rows = (await db.scalars(select(CapaR6SourceOrigin).join(
        CapaR6RootRevisionSource, CapaR6RootRevisionSource.source_id == CapaR6SourceOrigin.source_id
    ).where(CapaR6RootRevisionSource.revision_id == revision.revision_id,
            CapaR6RootRevisionSource.report_id == report_id,
            CapaR6SourceOrigin.report_id == report_id).limit(_MAX_SOURCES + 1)
      .execution_options(populate_existing=True))).all()
    if (len(origin_rows) > _MAX_SOURCES or len(origin_rows) != body.source_count
            or capa_d4_material.origin_digest(row.source_id for row in origin_rows) != body.origin_digest
            or body.binding_state != ("controlled" if origin_rows else "legacy_unattested")):
        raise ImpactMaterialUnavailable()
    refs = {}
    for row in origin_rows:
        if row.kind == "fmea_projection":
            from app.services.fmea_agent_sources import visible_fmea_source
            visible = await visible_fmea_source(db, scope, row.fmea_id)
            if (row.module != "fmea" or row.fmea_id != row.object_id or row.snapshot_id is not None
                    or not row.node_id or row.source_version_counter is None
                    or (visible.factory_id, visible.product_line_code) != (row.factory_id, row.product_line_code)):
                raise ImpactMaterialUnavailable()
        elif row.kind == "report_snapshot":
            snapshot = (await db.execute(select(
                CapaR6ReportSnapshot.report_id, CapaR6ReportSnapshot.kind, CapaR6ReportSnapshot.version,
            ).where(CapaR6ReportSnapshot.snapshot_id == row.snapshot_id))).one_or_none()
            if (row.module != "capa" or row.object_id != report_id or row.fmea_id is not None
                    or row.node_id is not None or row.source_version_counter is not None or snapshot is None
                    or (row.factory_id, row.product_line_code) != (proof.factory_id, proof.product_line_code)
                    or snapshot.report_id != report_id or snapshot.kind not in {"d2", "d3"}
                    or str(snapshot.version) != row.version or row.projection_id != f"capa.{snapshot.kind}.snapshot.v1"):
                raise ImpactMaterialUnavailable()
        else:
            raise ImpactMaterialUnavailable()
        refs[row.source_id] = ImpactSourceRef(source_id=row.source_id, module=row.module, object_id=row.object_id,
            projection_id=row.projection_id, version=row.version, factory_id=row.factory_id,
            product_line_code=row.product_line_code, snapshot_id=row.snapshot_id, node_id=row.node_id,
            source_version_counter=row.source_version_counter)
    return refs


def _coordinate(ref):
    return (ref.projection_id, str(ref.factory_id), ref.product_line_code,
            str(ref.object_id), ref.node_id, ref.version)


def _receipt_coordinate(source):
    return tuple(source[key] for key in
                 ("projection_id", "factory_id", "product_line_code", "fmea_id", "node_id", "node_hmac"))


async def _measure_sources(db, scope, tenant_id, proof, row, sources, root_refs, *, fresh):
    """Use the captured epochs. An older D5 receipt without one is not fresh input."""
    command = AgentD5Command
    if not await capa_r6_delivery.task_requires_r6_sidecar(db, row.task_id):
        raise ImpactMaterialUnavailable()
    receipts = (await db.execute(select(AgentD5BasisReceipt, command.run_id.label("command_run_id")).join(
        AgentD5CommandBasis, AgentD5CommandBasis.receipt_id == AgentD5BasisReceipt.receipt_id,
    ).join(command, command.command_id == AgentD5CommandBasis.command_id)
     .where(command.proposal_id == row.proposal_id)
     .limit(_MAX_SOURCES + 1).execution_options(populate_existing=True))).all()
    if not receipts or len(receipts) > _MAX_SOURCES:
        raise ImpactMaterialUnavailable()
    captured = {}
    root_epochs = {_coordinate(ref): ref.source_version_counter for ref in root_refs.values() if ref.module == "fmea"}
    for receipt, command_run_id in receipts:
        if (receipt.task_id != row.task_id or receipt.report_id != proof.report_id
                or receipt.revision_id != proof.revision_id or receipt.proof_id != proof.proof_id
                or receipt.tenant_generation != proof.tenant_generation or receipt.run_id != command_run_id):
            raise ImpactMaterialUnavailable()
        await capa_r6_delivery.validate_root_delivery_binding(db, receipt, tenant_id, scope=scope, fresh=fresh)
        sidecar = await db.get(CapaR6RootDeliveryBinding, receipt.receipt_id, populate_existing=True)
        if sidecar is None:
            raise ImpactMaterialUnavailable()
        epochs = root_epochs
        if len(sidecar.input_bindings) == 1 and sidecar.input_bindings[0].get("mode") == "legacy_root":
            epochs = {_receipt_coordinate(source): source["source_version_counter"]
                      for source in sidecar.input_bindings[0]["context_source_epochs"]}
        for source in receipt.sources:
            coordinate = _receipt_coordinate(source)
            epoch = epochs.get(coordinate)
            if type(epoch) is not int or (coordinate in captured and captured[coordinate] != epoch):
                raise ImpactMaterialUnavailable()
            captured[coordinate] = epoch
    refs = {}
    for source in sources:
        ref = ImpactSourceRef(source_id=source.source_id, module="fmea", object_id=source.fmea_id,
            projection_id=source.projection_id, version=source.node_hmac, factory_id=source.factory_id,
            product_line_code=source.product_line_code, node_id=source.node_id)
        coordinate = _coordinate(ref)
        if coordinate not in captured:
            raise ImpactMaterialUnavailable()
        refs[ref.source_id] = ref.model_copy(update={"source_version_counter": captured[coordinate]})
    if {_coordinate(ref) for ref in refs.values()} != set(captured):
        raise ImpactMaterialUnavailable()
    return refs


async def _measure_keys(db, report_id, revision_id, proof_id, history):
    # A new proof supersedes eligibility even on the same root revision.
    # Measures supported by the older proof remain formal history.
    query = select(CapaD5Measure.measure_id, CapaD5Measure.proposal_id, CapaD5Proposal.proof_id).join(
        CapaD5Proposal, CapaD5Proposal.proposal_id == CapaD5Measure.proposal_id,
    ).where(CapaD5Proposal.report_id == report_id, CapaD5Proposal.revision_id == revision_id,
            CapaD5Proposal.proof_id == proof_id)
    if history is not None:
        query = query.where(CapaD5Measure.measure_id.in_([key.measure_id for key in history.measures]))
    rows = (await db.execute(query.order_by(CapaD5Measure.measure_id).limit(_MAX_MEASURES + 1))).all()
    if len(rows) > _MAX_MEASURES:
        # The count includes measures whose sources we have not authorized.
        raise ImpactMaterialUnavailable()
    keys = {key.measure_id: key for key in history.measures} if history is not None else {}
    if history is not None and (len(keys) != len(history.measures) or set(keys) != {row.measure_id for row in rows}):
        raise ImpactMaterialUnavailable()
    result = {}
    for row in rows:
        correction = select(CapaD5MeasureRevision.revision_id, CapaD5MeasureRevision.report_id).where(
            CapaD5MeasureRevision.measure_id == row.measure_id)
        if history is None:
            correction_row = (await db.execute(
                correction.order_by(CapaD5MeasureRevision.revision_no.desc()).limit(1))).one_or_none()
        elif keys[row.measure_id].formal_revision is None:
            correction_row = None
        else:
            correction_row = (await db.execute(correction.where(
                CapaD5MeasureRevision.revision_id == keys[row.measure_id].formal_revision))).one_or_none()
            if correction_row is None:
                raise ImpactMaterialUnavailable()
        if correction_row is not None and correction_row.report_id != report_id:
            raise ImpactMaterialUnavailable()
        key = MeasureKey(measure_id=row.measure_id,
                         formal_revision=None if correction_row is None else correction_row.revision_id)
        result[key] = row
    return result


async def _metadata(db, scope, report_id, history=None):
    await capa_d4_material.require_current_egress_statement(db)
    access = await current_capa_access(db, scope)
    target = await current_capa_target_metadata(db, report_id, access[1], access[2])
    tenant = db.info.get("tenant_binding")
    if tenant is None:
        raise ImpactMaterialUnavailable()
    if history is None:
        await capa_d4_material.authorize_root(db, scope.user.user_id, report_id)
        await require_ordinary_capture_material(db, report_id)
    proof, revision = await _proof_and_revision(db, report_id, tenant.generation, history)
    if (proof.factory_id, proof.product_line_code) != (target.factory_id, target.product_line_code):
        raise ImpactMaterialUnavailable()
    verification_sources = await authorize_verifications(db, report_id, actor_id=scope.user.user_id,
                                                         verification_id=proof.verification_id)
    if not verification_sources:
        raise ImpactMaterialUnavailable()
    root_refs = await _revision_sources(db, scope, report_id, revision, proof)
    formal = await _measure_keys(db, report_id, revision.revision_id, proof.proof_id, history)
    _, visible_rows, proposal_sources = await capa_d5_measures._visible_metadata(
        db, scope, report_id, access, proposal_ids=[item.proposal_id for item in formal.values()])
    visible = {row.proposal_id: row for row in visible_rows if row.state == "adopted"}
    if any(item.proposal_id not in visible for item in formal.values()):
        raise ImpactMaterialUnavailable()
    if history is None:
        current_revision, _ = await capa_d4_material.require_root_freshness(db, scope.user.user_id, report_id)
        verification = (await db.execute(select(CapaRootCauseVerification.is_verified).where(
            CapaRootCauseVerification.verification_id == proof.verification_id,
            CapaRootCauseVerification.capa_id == report_id,
            CapaRootCauseVerification.factory_id == target.factory_id))).one_or_none()
        if (target.status not in _ASSESSABLE_STAGES or current_revision is None
                or current_revision.revision_id != revision.revision_id
                or verification is None or verification.is_verified is not True):
            raise ImpactMaterialNotReady("d4_not_verified")
        if not formal:
            raise ImpactMaterialNotReady("d5_not_adopted")
    elif not formal:
        raise ImpactMaterialUnavailable()

    all_sources = dict(root_refs)
    by_measure = {}
    for key, item in formal.items():
        row = visible[item.proposal_id]
        refs = await _measure_sources(db, scope, tenant.tenant_id, proof, row, proposal_sources[row.proposal_id],
                                      root_refs, fresh=history is None)
        all_sources.update(refs)
        by_measure[key.measure_id] = tuple(sorted(root_refs.keys() | refs.keys()))
        if len(all_sources) > _MAX_SOURCES:
            # Later measures have not passed signed receipt source checks.
            raise ImpactMaterialUnavailable()

    fmea_refs = [ref for ref in all_sources.values() if ref.module == "fmea"]
    coordinates = {(str(ref.object_id), ref.node_id, str(ref.factory_id), ref.product_line_code)
                   for ref in fmea_refs}
    if any((item["fmea_id"], item["cause_node_id"], item["factory_id"], item["product_line_code"])
           not in coordinates for item in verification_sources):
        raise ImpactMaterialUnavailable()
    primary = next((ref for ref in sorted(fmea_refs, key=lambda ref: ref.source_id)
        if _coordinate(ref) == (proof.source_projection_id, str(proof.factory_id), proof.product_line_code,
                                str(proof.fmea_id), proof.cause_node_id, proof.node_hmac)), None)
    if primary is None:
        raise ImpactMaterialUnavailable()
    if history is None:
        for item in formal.values():
            if not await capa_d5_measures._basis_current(db, scope, target, visible[item.proposal_id],
                                                         proposal_sources[item.proposal_id]):
                raise ImpactMaterialUnavailable()
    binding = CapaImpactBinding(tenant_id=tenant.tenant_id, tenant_generation=tenant.generation,
        report_id=report_id, factory_id=target.factory_id, product_line_code=target.product_line_code,
        root_revision=revision.revision_id, proof_id=proof.proof_id, verification_ref=proof.verification_id,
        verification_version=proof.verification_version, measures=tuple(formal),
        sources=tuple(sorted(all_sources.values(), key=lambda ref: ref.source_id)))
    return _MaterialMetadata(binding, primary, by_measure)


def _bounded(text):
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > _MAX_FIELD_BYTES:
        raise ImpactMaterialNotReady("too_large")
    return text


async def read_material(db, scope, report_id, *, expected: CapaImpactBinding | None = None) -> CapaImpactMaterial:
    """Project current formal material for an authorized employee identity."""
    try:
        before = await _metadata(db, scope, report_id)
        if expected is not None and expected != before.binding:
            raise ImpactMaterialUnavailable()
        root = _bounded(await capa_d4_material.read_root(db, scope.user.user_id, report_id))
        problem_snapshot = next((ref.snapshot_id for ref in before.binding.sources
            if ref.projection_id == "capa.d2.snapshot.v1"), None)
        problem = None
        if problem_snapshot is not None:
            value = await db.scalar(select(CapaR6ReportSnapshot.body).where(
                CapaR6ReportSnapshot.snapshot_id == problem_snapshot, CapaR6ReportSnapshot.report_id == report_id,
                func.octet_length(CapaR6ReportSnapshot.body) <= _MAX_FIELD_BYTES))
            if value is None:
                raise ImpactMaterialUnavailable()
            problem = value.strip() or None
        measures = []
        for key in before.binding.measures:
            current = await current_measure(db, key.measure_id, report_id)
            if key.formal_revision != current["correction_revision_id"]:
                raise ImpactMaterialUnavailable()
            measures.append(CapaImpactMeasure(key=key, adoption_ref=key.measure_id,
                revision_no=current["correction_revision_no"], text=_bounded(current["final_text"]),
                source_ids=before.by_measure[key.measure_id]))
        after = await _metadata(db, scope, report_id)
        if before.binding != after.binding or before.by_measure != after.by_measure:
            raise ImpactMaterialUnavailable()
        material = CapaImpactMaterial(binding=before.binding, root_cause=root, problem_description=problem,
                                      primary_source_id=before.primary.source_id, measures=tuple(measures))
        if len(material.model_dump_json().encode("utf-8")) > _MAX_MATERIAL_BYTES:
            raise ImpactMaterialNotReady("too_large")
        return material
    except (PermissionError, LookupError):
        raise ImpactMaterialUnavailable() from None


async def authorize_history(db, scope, binding: CapaImpactBinding) -> None:
    """Check the persisted binding against the reviewer's live authority.

    The existing verification adapter includes currently accumulated origins.
    It can conservatively hide a result when a verification gained new origins.
    Historical display needs an exact immutable verification-origin adapter
    before it can distinguish that case from loss of historical source access.
    """
    try:
        tenant = db.info.get("tenant_binding")
        if tenant is None or (binding.tenant_id, binding.tenant_generation) != (tenant.tenant_id, tenant.generation):
            raise ImpactMaterialUnavailable()
        historic = await _metadata(db, scope, binding.report_id, history=binding)
        if historic.binding != binding:
            raise ImpactMaterialUnavailable()
    except (PermissionError, LookupError, ImpactMaterialNotReady):
        raise ImpactMaterialUnavailable() from None
