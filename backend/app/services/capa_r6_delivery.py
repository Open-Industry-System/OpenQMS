"""Server-owned R6 report inputs, separate from R5's complete-text proof."""
import hashlib
import hmac

from sqlalchemy import select

from app.models.capa import CAPAEightD
from app.models.capa_r6 import (CapaR6ReportSnapshot, CapaR6RootDeliveryBinding,
    CapaR6RootRevisionBody, CapaR6RootRevisionSource, CapaR6SourceOrigin)
from app.services.capa_d4_material import authorize_root, require_root_freshness, origin_digest, material_version

UNAVAILABLE = 'D4 delivery unavailable; continue manual D5'


def logical_origin_groups(sources):
    """Keep every immutable reference; compare facts by their exact coordinates."""
    grouped = {}
    for source in sorted(sources, key=lambda item: str(item.source_id)):
        counter = source.source_version_counter
        key = (source.kind, source.module, source.object_id, source.projection_id, source.version,
            source.factory_id, source.product_line_code, source.snapshot_id, source.fmea_id, source.node_id,
            type(counter).__name__, counter)
        grouped.setdefault(key, []).append(source)
    return tuple(tuple(group) for group in grouped.values())


async def task_requires_r6_sidecar(db, task_id):
    """Classify immutable approved pins without requiring an enabled recipient."""
    from app.models.agent_model_deployment import AgentTaskModelBinding, AgentModelDeployment
    from app.services.agent_runtime import model_egress
    binding = await db.get(AgentTaskModelBinding, task_id, populate_existing=True)
    if binding is None:
        return False
    row = await db.get(AgentModelDeployment, binding.deployment_id, populate_existing=True)
    if (row is None or binding.config_hmac != row.config_hmac
            or not hmac.compare_digest(row.config_hmac, model_egress._digest(db, row))):
        raise PermissionError(UNAVAILABLE)
    return model_egress.deployment_profile(row) == model_egress.R6_PROFILE


async def validate_context_source_epochs(db, sources, captured, *, scope=None, fresh=True):
    """Exact actual-context coordinates; these are never inherited root origins."""
    import json
    from uuid import UUID
    from app.models.fmea import FMEADocument
    from app.services.capa_d5_proposals import SOURCE_KEYS
    from app.services.fmea_agent_sources import visible_fmea_source
    def key(source):
        return json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if (not isinstance(sources, list) or not sources or not isinstance(captured, list)
            or len(captured) != len(sources)):
        raise PermissionError(UNAVAILABLE)
    expected = {key(source) for source in sources if isinstance(source, dict) and set(source) == SOURCE_KEYS}
    if len(expected) != len(sources):
        raise PermissionError(UNAVAILABLE)
    seen = set()
    for entry in captured:
        if not isinstance(entry, dict) or set(entry) != SOURCE_KEYS | {'source_version_counter'}:
            raise PermissionError(UNAVAILABLE)
        counter = entry['source_version_counter']
        source = {name: entry[name] for name in SOURCE_KEYS}
        coordinate = key(source)
        if type(counter) is not int or counter < 0 or coordinate not in expected or coordinate in seen:
            raise PermissionError(UNAVAILABLE)
        seen.add(coordinate)
        try:
            fmea_id = UUID(source['fmea_id'])
            if scope is not None:
                visible = await visible_fmea_source(db, scope, fmea_id)
                if (str(visible.factory_id), visible.product_line_code) != (source['factory_id'], source['product_line_code']):
                    raise PermissionError(UNAVAILABLE)
            if fresh:
                current = await db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id == fmea_id))
                if type(current) is not int or current != counter:
                    raise PermissionError(UNAVAILABLE)
        except (ValueError, TypeError, KeyError):
            raise PermissionError(UNAVAILABLE) from None


def complete_root_input_binding(binding, context_epochs):
    if binding is not None and binding.get('mode') == 'legacy_root':
        return dict(binding, input_bindings=[dict(binding['input_bindings'][0], context_source_epochs=context_epochs)])
    return binding


async def require_current_root_use(db, identity):
    """Even context-free rounds retain every delivered R6 context's epochs."""
    from app.services.capa_d4_material import root_metadata
    from app.services.agent_runtime import model_egress
    _, sources = await root_metadata(db, identity.task.target_capa_id)
    r6 = identity.trial is not None and identity.trial.profile == model_egress.R6_PROFILE
    if sources or r6:
        from app.services.capa_d5_proposals import _current_basis
        target, proof = await _current_basis(db, identity)
        if r6:
            from app.models.agent_d5_basis import AgentD5BasisReceipt
            receipts = list(await db.scalars(select(AgentD5BasisReceipt).where(
                AgentD5BasisReceipt.run_id == identity.run.run_id)))
            for receipt in receipts:
                await validate_root_delivery_binding(db, receipt, identity.binding.tenant_id,
                    scope=identity.scope, identity=identity, target=target, proof=proof)


async def require_root_delivery(db, identity, target, proof):
    """No protected body until full origins, exact grants and recipient agree."""
    from app.services.agent_runtime import runtime_access, model_egress
    revision, sources = await authorize_root(db, identity.task.executor_user_id, target.report_id)
    r6 = identity.trial is not None and identity.trial.profile == model_egress.R6_PROFILE
    if not sources and not r6:
        return None
    if not r6:
        raise PermissionError(UNAVAILABLE)
    body = (await db.execute(select(CapaR6RootRevisionBody.binding_state, CapaR6RootRevisionBody.source_count,
        CapaR6RootRevisionBody.origin_digest).where(CapaR6RootRevisionBody.revision_id == revision.revision_id,
            CapaR6RootRevisionBody.report_id == target.report_id))).one_or_none() if revision else None
    if body is None:
        raise PermissionError(UNAVAILABLE)
    if revision is None or revision.revision_id != proof.revision_id:
        raise PermissionError(UNAVAILABLE)
    if not sources:
        if body.binding_state != 'legacy_unattested' or body.source_count != 0 or body.origin_digest != origin_digest(()):
            raise PermissionError(UNAVAILABLE)
        # No capture or invented K2/K3/origin facts on a read of manual material.
        recipient = await model_egress.task_deployment(db, identity.task)
        if model_egress.deployment_profile(recipient) != model_egress.R6_PROFILE:
            raise PermissionError(UNAVAILABLE)
        authority = await runtime_access.authorize_task(db, identity.task, identity.installation)
        for capability in ('capa.d2.snapshot.v1', 'capa.d3.snapshot.v1'):
            runtime_access.require_capability(identity, capability)
            if not any(c.id == capability and c.allowed for c in authority.capabilities):
                raise PermissionError(UNAVAILABLE)
        runtime_access.require_delivery(identity, 'restricted', 'masked', controlled_egress=True)
        metadata = dict(version=1, mode='legacy_root', report_inputs=[], context_source_epochs=[],
            executor_id=str(identity.task.executor_user_id), installation_id=str(identity.installation.installation_id),
            task_id=str(identity.task.task_id), recipient_id=str(recipient.deployment_id), recipient_hmac=recipient.config_hmac)
        return dict(mode='legacy_root', report_id=str(target.report_id), revision_id=str(revision.revision_id),
            origin_digest=origin_digest(()), source_ids=[], material_version=await material_version(db, target.report_id),
            input_bindings=[metadata])
    logical = [group[0] for group in logical_origin_groups(sources)]
    external = [s for s in logical if s.kind == 'fmea_projection']
    inputs = [s for s in logical if s.kind == 'report_snapshot']
    if (len(external) != 1 or len(inputs) != 2 or len(logical) != 3
            or {s.projection_id for s in inputs} != {'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1'}):
        raise PermissionError(UNAVAILABLE)
    source = external[0]
    if (source.fmea_id, source.node_id, source.version, source.projection_id) != (
            proof.fmea_id, proof.cause_node_id, proof.node_hmac, proof.source_projection_id):
        raise PermissionError(UNAVAILABLE)
    # Re-running canonical task authority checks the original plugin AND task
    # grant. Broad plugin scopes never become eligible merely by narrowing T.
    authority = await runtime_access.authorize_task(db, identity.task, identity.installation)
    if authority.trial is None or authority.trial.profile != model_egress.R6_PROFILE:
        raise PermissionError(UNAVAILABLE)
    for source in inputs:
        runtime_access.require_capability(identity, source.projection_id)
        if not any(c.id == source.projection_id and c.allowed for c in authority.capabilities):
            raise PermissionError(UNAVAILABLE)
    runtime_access.require_delivery(identity, 'restricted', 'masked', controlled_egress=True)
    recipient = await model_egress.task_deployment(db, identity.task)
    if model_egress.deployment_profile(recipient) != model_egress.R6_PROFILE:
        raise PermissionError(UNAVAILABLE)
    await require_root_freshness(db, identity.task.executor_user_id, target.report_id)
    bound = []
    for source in sorted(inputs, key=lambda s: s.projection_id):
        snapshot = await db.get(CapaR6ReportSnapshot, source.snapshot_id, populate_existing=True)
        kind = {'capa.d2.snapshot.v1': 'd2', 'capa.d3.snapshot.v1': 'd3'}[source.projection_id]
        if (snapshot is None or snapshot.report_id != target.report_id or snapshot.kind != kind
                or source.version != str(snapshot.version)):
            raise PermissionError(UNAVAILABLE)
        column = {'d2': CAPAEightD.d2_description, 'd3': CAPAEightD.d3_interim}[kind]
        current_body = await db.scalar(select(column).where(CAPAEightD.report_id == target.report_id))
        if (current_body or '') != snapshot.body:
            raise PermissionError(UNAVAILABLE)
        bound.append(dict(source_id=str(source.source_id), snapshot_id=str(snapshot.snapshot_id),
            report_id=str(target.report_id), projection_id=source.projection_id, version=str(snapshot.version),
            digest=hashlib.sha256(snapshot.body.encode()).hexdigest(),
            executor_id=str(identity.task.executor_user_id), installation_id=str(identity.installation.installation_id),
            task_id=str(identity.task.task_id), recipient_id=str(recipient.deployment_id),
            recipient_hmac=recipient.config_hmac, external_source_id=str(external[0].source_id),
            source_version_counter=external[0].source_version_counter))
    return dict(report_id=str(target.report_id), revision_id=str(revision.revision_id),
        origin_digest=origin_digest(s.source_id for s in sources),
        source_ids=sorted(str(s.source_id) for s in sources),
        material_version=await material_version(db, target.report_id), input_bindings=bound)


def _sidecar_payload(sidecar, tenant_id):
    return dict(tenant_id=str(tenant_id), receipt_id=str(sidecar.receipt_id),
        report_id=str(sidecar.report_id), revision_id=str(sidecar.revision_id),
        origin_digest=sidecar.origin_digest, input_bindings=sidecar.input_bindings)


async def add_root_delivery_binding(db, identity, receipt, root_binding):
    from app.services.agent_runtime.d4_text_delivery import _digest
    if root_binding is None:
        return
    sidecar = CapaR6RootDeliveryBinding(receipt_id=receipt.receipt_id, report_id=receipt.report_id,
        revision_id=receipt.revision_id, origin_digest=root_binding['origin_digest'],
        input_bindings=root_binding['input_bindings'])
    sidecar.binding_hmac = _digest('openqms.r6.root-delivery.v1', _sidecar_payload(sidecar, identity.binding.tenant_id))
    db.add(sidecar)
    await db.flush()


async def validate_root_delivery_binding(db, receipt, tenant_id, *, scope, identity=None, target=None, proof=None, fresh=False):
    """Historical integrity/current read ACL first; freshness is opt-in for use."""
    from app.services.agent_runtime.d4_text_delivery import _digest
    from app.services.capa_d5_proposals import _receipt_payload
    from app.services.fmea_agent_sources import visible_fmea_source
    from app.services.capa_current_access import current_capa_actor_access, current_capa_target_metadata
    from app.core.permissions import PermissionLevel
    body = (await db.execute(select(CapaR6RootRevisionBody.binding_state,
        CapaR6RootRevisionBody.origin_digest, CapaR6RootRevisionBody.source_count).where(
        CapaR6RootRevisionBody.revision_id == receipt.revision_id,
        CapaR6RootRevisionBody.report_id == receipt.report_id))).one_or_none()
    required = await task_requires_r6_sidecar(db, receipt.task_id)
    if body is None:
        if required:
            raise PermissionError(UNAVAILABLE)
        return
    if body.binding_state != 'controlled' and not required:
        return
    if not hmac.compare_digest(receipt.basis_hmac,
            _digest('openqms.d5.delivered-basis.v1', _receipt_payload(receipt, tenant_id))):
        raise PermissionError(UNAVAILABLE)
    if scope is not None:
        factories, lines = await current_capa_actor_access(db, scope.user.user_id, PermissionLevel.VIEW)
        await current_capa_target_metadata(db, receipt.report_id, factories, lines)
    origins = list(await db.scalars(select(CapaR6SourceOrigin).join(CapaR6RootRevisionSource,
        CapaR6RootRevisionSource.source_id == CapaR6SourceOrigin.source_id).where(
        CapaR6RootRevisionSource.revision_id == receipt.revision_id,
        CapaR6SourceOrigin.report_id == receipt.report_id)))
    if len(origins) != body.source_count or origin_digest(s.source_id for s in origins) != body.origin_digest:
        raise PermissionError(UNAVAILABLE)
    for source in origins:
        if source.kind == 'fmea_projection' and scope is not None:
            visible = await visible_fmea_source(db, scope, source.fmea_id)
            if (visible.factory_id, visible.product_line_code) != (source.factory_id, source.product_line_code):
                raise PermissionError(UNAVAILABLE)
    sidecar = await db.get(CapaR6RootDeliveryBinding, receipt.receipt_id, populate_existing=True)
    if (sidecar is None or sidecar.report_id != receipt.report_id or sidecar.revision_id != receipt.revision_id
            or sidecar.origin_digest != body.origin_digest or not hmac.compare_digest(sidecar.binding_hmac,
                _digest('openqms.r6.root-delivery.v1', _sidecar_payload(sidecar, tenant_id)))):
        raise PermissionError(UNAVAILABLE)
    if body.binding_state == 'legacy_unattested':
        if origins or body.source_count != 0 or body.origin_digest != origin_digest(()):
            raise PermissionError(UNAVAILABLE)
        if not isinstance(sidecar.input_bindings, list) or len(sidecar.input_bindings) != 1:
            raise PermissionError(UNAVAILABLE)
        metadata = sidecar.input_bindings[0]
        keys = {'version', 'mode', 'report_inputs', 'context_source_epochs', 'executor_id',
            'installation_id', 'task_id', 'recipient_id', 'recipient_hmac'}
        if (not isinstance(metadata, dict) or set(metadata) != keys or type(metadata['version']) is not int
                or metadata['version'] != 1 or metadata['mode'] != 'legacy_root' or metadata['report_inputs'] != []
                or metadata['task_id'] != str(receipt.task_id)):
            raise PermissionError(UNAVAILABLE)
        from app.models.agent_task import AgentTask
        from app.models.agent_model_deployment import AgentTaskModelBinding, AgentModelDeployment
        task = await db.get(AgentTask, receipt.task_id, populate_existing=True)
        deployment_binding = await db.get(AgentTaskModelBinding, receipt.task_id, populate_existing=True)
        deployment = await db.get(AgentModelDeployment, deployment_binding.deployment_id, populate_existing=True)
        if (task is None or metadata['executor_id'] != str(task.executor_user_id)
                or metadata['installation_id'] != str(task.preferred_installation_id)
                or metadata['recipient_id'] != str(deployment.deployment_id)
                or metadata['recipient_hmac'] != deployment.config_hmac):
            raise PermissionError(UNAVAILABLE)
        await validate_context_source_epochs(db, receipt.sources, metadata['context_source_epochs'],
            scope=scope, fresh=fresh or identity is not None)
        if identity is not None:
            current = complete_root_input_binding(await require_root_delivery(db, identity, target, proof), metadata['context_source_epochs'])
            if (current is None or current.get('mode') != 'legacy_root'
                    or current['revision_id'] != str(receipt.revision_id)
                    or current['origin_digest'] != sidecar.origin_digest or current['input_bindings'] != sidecar.input_bindings):
                raise PermissionError(UNAVAILABLE)
        return
    logical = [group[0] for group in logical_origin_groups(origins)]
    inputs = {str(s.source_id): s for s in logical if s.kind == 'report_snapshot'}
    external = [s for s in logical if s.kind == 'fmea_projection']
    if len(inputs) != 2 or len(external) != 1 or len(logical) != 3:
        raise PermissionError(UNAVAILABLE)
    if not isinstance(sidecar.input_bindings, list) or len(sidecar.input_bindings) != len(inputs):
        raise PermissionError(UNAVAILABLE)
    if {item.get('source_id') for item in sidecar.input_bindings if isinstance(item, dict)} != set(inputs):
        raise PermissionError(UNAVAILABLE)
    for item in sidecar.input_bindings:
        source = inputs[item['source_id']]
        snapshot = await db.get(CapaR6ReportSnapshot, source.snapshot_id, populate_existing=True)
        if (snapshot is None or item.get('report_id') != str(receipt.report_id)
                or item.get('snapshot_id') != str(source.snapshot_id) or item.get('version') != source.version
                or item.get('projection_id') != source.projection_id
                or item.get('digest') != hashlib.sha256(snapshot.body.encode()).hexdigest()):
            raise PermissionError(UNAVAILABLE)
        counter = external[0].source_version_counter
        if counter is not None and (type(item.get('source_version_counter')) is not int
                or item['source_version_counter'] != counter
                or item.get('external_source_id') != str(external[0].source_id)):
            raise PermissionError(UNAVAILABLE)
    external_source = external[0]
    expected_source = dict(projection_id=external_source.projection_id, factory_id=str(external_source.factory_id),
        product_line_code=external_source.product_line_code, fmea_id=str(external_source.fmea_id),
        node_id=external_source.node_id, node_hmac=external_source.version)
    if receipt.sources != [expected_source]:
        raise PermissionError(UNAVAILABLE)
    if external_source.source_version_counter is not None or fresh or identity is not None:
        captured = [dict(expected_source, source_version_counter=external_source.source_version_counter)]
        await validate_context_source_epochs(db, receipt.sources, captured, scope=scope, fresh=fresh or identity is not None)
    if fresh:
        for source in inputs.values():
            snapshot = await db.get(CapaR6ReportSnapshot, source.snapshot_id, populate_existing=True)
            latest = await db.scalar(select(CapaR6ReportSnapshot.version).where(
                CapaR6ReportSnapshot.report_id == receipt.report_id, CapaR6ReportSnapshot.kind == snapshot.kind)
                .order_by(CapaR6ReportSnapshot.version.desc()).limit(1))
            if str(latest) != source.version:
                raise PermissionError(UNAVAILABLE)
    if identity is not None:
        current = await require_root_delivery(db, identity, target, proof)
        if (current is None or current['origin_digest'] != sidecar.origin_digest
                or current['revision_id'] != str(receipt.revision_id)
                or current['input_bindings'] != sidecar.input_bindings):
            raise PermissionError(UNAVAILABLE)
