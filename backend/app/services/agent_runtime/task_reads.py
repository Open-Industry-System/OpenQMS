"""Bounded own-user activity and current fixed-target installation choices."""
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import select

from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.capa import CAPAEightD
from app.models.agent_readonly_control import AgentTaskControl, AgentTaskUpdate
from app.models.agent_task import AgentRun, AgentTaskMessage
from app.schemas.agent_control import ActivityQuery, ActivityPage, InstallationDirectory, InstallationChoice
from app.schemas.agent_plugin import PluginManifest
from app.services.agent_runtime import checkpoint_service, readonly_delivery, task_service
from app.services.agent_runtime.task_controls import _current_run, _task_binding


async def _choices(db, scope, report_id):
    levels, factories, lines = await task_service._current_access(db, scope)
    target = await task_service._target(db, report_id, factories, lines)
    with db.no_autoflush:
        plugins = list((await db.scalars(select(AgentPluginInstallation).where(
            AgentPluginInstallation.enabled.is_(True)).order_by(AgentPluginInstallation.plugin_key,
            AgentPluginInstallation.plugin_version, AgentPluginInstallation.installation_id)
            .execution_options(populate_existing=True))).all())
        grants = list((await db.scalars(select(AgentPluginGrant)
            .execution_options(populate_existing=True))).all())
    choices = []
    for plugin in plugins:
        try:
            manifest = PluginManifest.model_validate(plugin.manifest)
        except ValidationError:
            continue
        # R1 canonical intersection with a transient grant description only.
        # Never attach hypothetical Tasks/grants to the session or persist them.
        trial = task_service.trial_for_target(db, plugin, scope.user.user_id, target)
        _, ready = task_service._read_grants(None, target, manifest, levels, factories, lines,
            [row for row in grants if row.installation_id == plugin.installation_id], trial=trial)
        if ready:
            choices.append(InstallationChoice(installation_id=plugin.installation_id,
                plugin_key=plugin.plugin_key, plugin_version=plugin.plugin_version))
    return choices


async def list_installations(db, scope, report_id: UUID) -> dict:
    await _choices(db, scope, report_id)
    await _choices(db, scope, report_id)
    # After materialization, one statement reloads actual target coordinates,
    # enabled installation/version/manifest and grants together. A late User
    # permission check alone cannot validate a candidate derived for an old PL.
    with db.no_autoflush:
        rows = (await db.execute(select(CAPAEightD, AgentPluginInstallation, AgentPluginGrant)
            .select_from(CAPAEightD).outerjoin(AgentPluginInstallation,
                AgentPluginInstallation.enabled.is_(True)).outerjoin(AgentPluginGrant,
                AgentPluginGrant.installation_id == AgentPluginInstallation.installation_id)
            .where(CAPAEightD.report_id == report_id)
            .order_by(AgentPluginInstallation.plugin_key, AgentPluginInstallation.plugin_version,
                AgentPluginInstallation.installation_id, AgentPluginGrant.grant_id)
            .execution_options(populate_existing=True))).all()
    levels, factories, lines = await task_service._current_access(db, scope)
    if not rows:
        raise LookupError("8D report not found")
    target = rows[0][0]
    if ((factories.accessible_factory_ids is not None
            and target.factory_id not in factories.accessible_factory_ids)
            or (lines.mode != "ALL" and target.product_line_code not in (lines.codes or []))):
        raise LookupError("8D report not found")
    plugins, grants = {}, {}
    for _, plugin, grant in rows:
        if plugin is not None:
            plugins[plugin.installation_id] = plugin
            if grant is not None:
                grants.setdefault(plugin.installation_id, []).append(grant)
    choices = []
    for plugin_id, plugin in plugins.items():
        try:
            manifest = PluginManifest.model_validate(plugin.manifest)
        except ValidationError:
            continue
        trial = task_service.trial_for_target(db, plugin, scope.user.user_id, target)
        _, ready = task_service._read_grants(None, target, manifest, levels, factories, lines,
            grants.get(plugin_id, []), trial=trial)
        if ready:
            choices.append(InstallationChoice(installation_id=plugin_id,
                plugin_key=plugin.plugin_key, plugin_version=plugin.plugin_version))
    return InstallationDirectory(items=choices).model_dump(mode="json")


async def _run(db, task, run_id):
    with db.no_autoflush:
        row = await db.scalar(select(AgentRun).where(AgentRun.run_id == run_id)
            .execution_options(populate_existing=True))
        installation = None if row is None else await db.scalar(select(AgentPluginInstallation.installation_id)
            .where(AgentPluginInstallation.installation_id == row.installation_id))
    if (row is None or row.task_id != task.task_id
            or row.installation_id != task.preferred_installation_id or installation is None):
        raise PermissionError("Activity association unavailable")
    return row


async def _batch(db, task, batch_id):
    with db.no_autoflush:
        rows = list((await db.scalars(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == task.task_id, AgentTaskMessage.delivery_batch_id == batch_id)
            .order_by(AgentTaskMessage.sequence).limit(21)
            .execution_options(populate_existing=True))).all())
        runs = list((await db.scalars(select(AgentRun).where(AgentRun.task_id == task.task_id)
            .execution_options(populate_existing=True))).all())
    if (not 1 <= len(rows) <= 20
            or [row.sequence for row in rows] != list(range(rows[0].sequence, rows[0].sequence+len(rows)))
            or any(row.author_id != task.executor_user_id or row.sensitivity != "restricted"
                or row.delivery_epoch is None or row.delivery_epoch < 0
                or row.delivery_epoch != rows[0].delivery_epoch
                or row.state not in ("claimed", "accepted") for row in rows)):
        raise PermissionError("Message batch unavailable")
    epoch, first = rows[0].delivery_epoch, rows[0].sequence
    matches = [run for run in runs if run.installation_id == task.preferred_installation_id
        and run.lease_epoch >= epoch and batch_id == uuid5(run.run_id, f"agent-message-batch:{epoch}:{first}")]
    if len(matches) != 1:
        raise PermissionError("Message batch unavailable")
    await _run(db, task, matches[0].run_id)
    if any(row.state == "accepted" and row.sequence > matches[0].accepted_message_seq for row in rows):
        raise PermissionError("Message batch unavailable")
    return rows


async def _materialize(db, scope, task, pointer):
    kind, object_id = pointer.kind, pointer.object_id
    if kind == "message":
        with db.no_autoflush:
            row = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.message_id == object_id)
                .execution_options(populate_existing=True))
        if (row is None or row.task_id != task.task_id or row.author_id != task.executor_user_id
                or row.sensitivity != "restricted" or row.state not in ("queued", "claimed", "accepted")):
            raise PermissionError("Message unavailable")
        if row.state != "queued":
            if row.delivery_batch_id is None:
                raise PermissionError("Message batch unavailable")
            await _batch(db, task, row.delivery_batch_id)
        elif row.delivery_batch_id is not None or row.delivery_epoch is not None:
            raise PermissionError("Message batch unavailable")
        data = dict(message_id=row.message_id, sequence=row.sequence, author_id=row.author_id,
            content=row.content, data_class="restricted", state="received" if row.state == "accepted" else row.state)
    elif kind == "ack":
        rows = await _batch(db, task, object_id)
        if not any(row.state == "accepted" for row in rows):
            raise PermissionError("Message acknowledgement unavailable")
        data = dict(batch_id=object_id, state="received")
    elif kind in ("run_created", "claim", "finish"):
        row = await _run(db, task, object_id)
        if kind == "finish" and row.status not in ("completed", "failed"):
            raise PermissionError("Run finish unavailable")
        if kind == "claim" and row.lease_epoch < 1:
            raise PermissionError("Run claim unavailable")
        data = dict(run_id=row.run_id, installation_id=row.installation_id,
            plugin_version=row.plugin_version, run_status=row.status, lease_epoch=row.lease_epoch)
    elif kind == "control":
        with db.no_autoflush:
            row = await db.scalar(select(AgentTaskControl).where(AgentTaskControl.control_id == object_id)
                .execution_options(populate_existing=True))
        if row is None or row.task_id != task.task_id or row.action not in ("pause", "resume", "cancel", "restart"):
            raise PermissionError("Control unavailable")
        if row.run_id is None:
            if row.action != "cancel" or row.resulting_run_id is not None or row.expected_epoch is not None:
                raise PermissionError("Control unavailable")
        else:
            await _run(db, task, row.run_id)
            if row.expected_epoch is None or row.expected_epoch < 0:
                raise PermissionError("Control unavailable")
        if row.resulting_run_id is not None:
            await _run(db, task, row.resulting_run_id)
        if row.action == "restart":
            if row.resulting_run_id is None or row.resulting_run_id == row.run_id or row.checkpoint_id is None:
                raise PermissionError("Control unavailable")
            cp = await checkpoint_service.get_checkpoint_for_view(db, scope, task.task_id, row.checkpoint_id)
            if cp["run_id"] != str(row.run_id):
                raise PermissionError("Control unavailable")
        elif row.checkpoint_id is not None or row.resulting_run_id != row.run_id:
            raise PermissionError("Control unavailable")
        data = dict(control_id=row.control_id, action=row.action, run_id=row.run_id,
            resulting_run_id=row.resulting_run_id, checkpoint_id=row.checkpoint_id)
    elif kind == "result":
        data = await readonly_delivery.get_result_for_view(db, scope, task.task_id, object_id)
    elif kind == "event":
        data = await readonly_delivery.get_event_for_view(db, scope, task.task_id, object_id)
    elif kind == "checkpoint":
        data = await checkpoint_service.get_checkpoint_for_view(db, scope, task.task_id, object_id)
        if data["update_sequence"] != pointer.sequence:
            raise PermissionError("Checkpoint association unavailable")
    else:
        raise PermissionError("Activity unavailable")
    return dict(sequence=pointer.sequence, kind=kind, created_at=pointer.created_at, data=data)


async def _final_sources(db, scope, task, items):
    """After the last content/Run read, recheck every actual source association."""
    from app.models.agent_runtime_event import AgentResult, AgentResultReceipt, AgentRunEvent, AgentEventReceipt
    from app.models.agent_readonly_control import AgentReadonlyCheckpoint

    for item in items:
        kind, data = item["kind"], item["data"]
        if kind in ("result", "event"):
            model, link = (AgentResult, AgentResultReceipt) if kind == "result" else (AgentRunEvent, AgentEventReceipt)
            id_name = "result_id" if kind == "result" else "event_id"
            output_id = UUID(str(data[id_name]))
            with db.no_autoflush:
                row = await db.scalar(select(model).where(getattr(model, id_name) == output_id)
                    .execution_options(populate_existing=True))
            if row is None or row.task_id != task.task_id or str(row.run_id) != str(data["run_id"]):
                raise PermissionError("Source unavailable")
            if ((kind == "result" and row.data_class != "restricted")
                    or (kind == "event" and row.event_type != data["event_type"])):
                raise PermissionError("Source unavailable")
            await _run(db, task, row.run_id)
            identifiers = await readonly_delivery._stored_sources(db, link, getattr(link, id_name), output_id)
            if sorted(map(str, identifiers)) != sorted(source["receipt_id"] for source in data["sources"]):
                raise PermissionError("Source unavailable")
            if identifiers:
                receipts = await readonly_delivery.admit_historical_sources(db, scope, task, row.run_id, identifiers)
                if readonly_delivery._source_metadata(receipts) != data["sources"]:
                    raise PermissionError("Source unavailable")
            elif kind != "event" or row.event_type != "progress":
                raise PermissionError("Source unavailable")
        elif kind == "checkpoint" or (kind == "control" and data["checkpoint_id"] is not None):
            checkpoint_id = UUID(str(data["checkpoint_id"]))
            with db.no_autoflush:
                row = await db.scalar(select(AgentReadonlyCheckpoint).where(
                    AgentReadonlyCheckpoint.checkpoint_id == checkpoint_id)
                    .execution_options(populate_existing=True))
            if row is None or row.task_id != task.task_id:
                raise PermissionError("Source unavailable")
            await _run(db, task, row.run_id)
            receipts = await checkpoint_service._historical_sources(db, scope, task, row)
            if kind == "checkpoint":
                actual = checkpoint_service._metadata(row, receipts)
                if actual != {name: data[name] for name in actual}:
                    raise PermissionError("Checkpoint association unavailable")
            elif str(row.run_id) != str(data["run_id"]):
                raise PermissionError("Checkpoint association unavailable")


async def get_activity(db, scope, task_id: UUID, *, before_sequence=None,
                       window_end_sequence=None, page_size=50) -> dict:
    request = ActivityQuery(before_sequence=before_sequence,
        window_end_sequence=window_end_sequence, page_size=page_size)
    task = await task_service.get_task_for_view(db, scope, task_id)
    binding = _task_binding(task)
    query = select(AgentTaskUpdate).where(AgentTaskUpdate.task_id == task_id)
    # bigint max+1 is a valid exclusive boundary but must never reach asyncpg.
    if request.before_sequence is not None and request.before_sequence <= 9223372036854775807:
        query = query.where(AgentTaskUpdate.sequence < request.before_sequence)
    if request.window_end_sequence is not None:
        query = query.where(AgentTaskUpdate.sequence <= request.window_end_sequence)
    with db.no_autoflush:
        rows = list((await db.scalars(query.order_by(AgentTaskUpdate.sequence.desc())
            .limit(request.page_size+1).execution_options(populate_existing=True))).all())
    window = request.window_end_sequence if request.window_end_sequence is not None else (rows[0].sequence if rows else 0)
    more, page = len(rows) > request.page_size, rows[:request.page_size]
    try:
        # First materialize all content, then freshly reload every returned object
        # and actual source association. No partial page ever leaves this boundary.
        for pointer in page:
            await _materialize(db, scope, task, pointer)
        task = await task_service.get_task_for_view(db, scope, task_id)
        if _task_binding(task) != binding:
            raise PermissionError("Activity association unavailable")
        items = [await _materialize(db, scope, task, pointer) for pointer in reversed(page)]
        run = await _current_run(db, task_id)
        if run is not None:
            run = await _run(db, task, run.run_id)
        await _final_sources(db, scope, task, items)
        task = await task_service.get_task_for_view(db, scope, task_id)
        if _task_binding(task) != binding:
            raise PermissionError("Activity association unavailable")
        return ActivityPage(task_id=task_id, task_status=task.status,
            run_id=None if run is None else run.run_id, run_status=None if run is None else run.status,
            lease_epoch=None if run is None else run.lease_epoch,
            window_end_sequence=window, next_before_sequence=page[-1].sequence if more else None,
            items=items).model_dump(mode="json")
    except (LookupError, ValidationError):
        # Corrupt/missing pointers and source objects reveal no object IDs/cursor.
        raise PermissionError("Activity unavailable") from None
