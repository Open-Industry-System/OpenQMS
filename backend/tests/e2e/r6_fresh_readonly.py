"""Registered generic GET/SQL-only C9 verifier; no module-level app activity.

All identities come from the authenticated fresh execution. No model, browser,
export or business write is permitted. Private evidence output is intentional.
"""
import hashlib
import io
import json
from pathlib import Path
from uuid import UUID
import zipfile
from xml.etree import ElementTree

INTERFACE = 'r6.c9-readonly.v1'
ORIGINAL = HERE = None
REPORT = MEASURE = None
FACTS = None
PRIOR = None


def configure(original, output, facts, prior=None):
    global ORIGINAL, HERE, FACTS, PRIOR, REPORT, MEASURE
    ORIGINAL, HERE = Path(original).resolve(), Path(output).resolve()
    assert HERE != ORIGINAL, 'raw JUnit-bound chain directory cannot be a reader output'
    assert type(facts['chain']['live_provider']) is bool
    FACTS, PRIOR = facts, prior
    REPORT, MEASURE = facts['chain']['report_id'], facts['chain']['measure_id']


def rows_sorted(rows):
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


def ReadOnlyExercise():
    from tests.e2e.r6_exercise import Exercise
    from app.core.tenant_transaction import TenantBinding

    class Reader(Exercise):
        def __init__(self):
            super().__init__()
            assert self.directory.resolve() == ORIGINAL and self.data['report_id'] == REPORT
            self.output = HERE
            self.allowed = set()
            self.violations = []

        def binding(self):
            return TenantBinding(UUID(self.data['tenant_id']), self.data['schema'], self.data['generation'], 'business')

        async def request(self, method, path, body=None, *, actor='qe', expected=200):
            if method != 'GET' or path not in self.allowed or actor not in self.data['actors'] or body is not None:
                self.violations.append(dict(method=method, path=path, actor=actor))
                raise AssertionError('Registered reader forbids business requests')
            return await super().request(method, path, actor=actor, expected=expected)

        async def browser(self, *args, **kwargs):
            raise AssertionError('Registered reader cannot start browser actions')

    return Reader()


async def baseline(exercise):
    """Read-only exact immutable model/input/source/command evidence, not global counts."""
    from sqlalchemy import text
    from app.database import tenant_async_session
    d4=FACTS['chain']['d4_task']
    TASK=FACTS['chain']['d5_task']
    tasks=[UUID(d4),UUID(TASK)];identifier=UUID(REPORT)
    async with tenant_async_session(binding=exercise.binding()) as db:
        values={}
        report_tables=['capa_r6_report_snapshots','capa_r6_root_revision_bodies','capa_d4_root_cause_revisions','capa_r6_root_revision_sources','capa_d4_candidates','capa_r6_source_origins','agent_d4_input_receipts','capa_d4_root_cause_source_proofs',
            'agent_d5_basis_receipts','capa_r6_root_delivery_bindings','agent_d4_candidate_commands']
        task_tables=['agent_tasks','agent_projection_receipts','agent_run_events','agent_results','agent_d5_commands','agent_task_messages','agent_runs','agent_task_model_bindings',
            'agent_d4_recovery_checkpoints','agent_d5_checkpoint_positions','agent_task_grants']
        for table in report_tables:
            values[table]=rows_sorted([row[0] for row in await db.execute(text(
                f'SELECT to_jsonb(t) FROM {table} t WHERE report_id=:id'),dict(id=identifier))])
        for table in task_tables:
            values[table]=rows_sorted([row[0] for row in await db.execute(text(
                f'SELECT to_jsonb(t) FROM {table} t WHERE task_id=ANY(CAST(:tasks AS uuid[]))'),dict(tasks=tasks))])
        values['agent_task_derived_source_scopes']=rows_sorted([row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_task_derived_source_scopes t WHERE task_grant_id IN (SELECT grant_id FROM agent_task_grants WHERE task_id=ANY(CAST(:tasks AS uuid[])))'),dict(tasks=tasks))])
        values['d5_command_basis']=rows_sorted([row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_d5_command_basis t WHERE command_id IN (SELECT command_id FROM agent_d5_commands WHERE task_id=ANY(CAST(:tasks AS uuid[])))'),dict(tasks=tasks))])
        values['prior_d4_confirmation']=rows_sorted([row[0] for row in await db.execute(text(
            "SELECT to_jsonb(t) FROM capa_r6_staff_receipts t WHERE report_id=:id AND operation='d4_confirm'"),dict(id=identifier))])
        assert len(values['prior_d4_confirmation'])==1
        values['model_egress_audit']=rows_sorted([row[0] for row in await db.execute(text(
            "SELECT to_jsonb(t) FROM audit_logs t WHERE action LIKE 'MODEL_EGRESS_%' AND (record_id=ANY(CAST(:tasks AS uuid[])) OR changed_fields->>'task_id'=ANY(CAST(:strings AS text[])))"),dict(tasks=tasks,strings=[str(v) for v in tasks]))])
        values['all_tenant_model_egress_audit']=rows_sorted([row[0] for row in await db.execute(text("SELECT to_jsonb(t) FROM audit_logs t WHERE action LIKE 'MODEL_EGRESS_%'"))])
        values['restricted_deliveries']=rows_sorted([row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_restricted_projection_receipts t WHERE task_id=ANY(CAST(:tasks AS uuid[]))'),dict(tasks=tasks))])
        values['installations']=rows_sorted([row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_plugin_installations t WHERE installation_id IN (SELECT preferred_installation_id FROM agent_tasks WHERE task_id=ANY(CAST(:tasks AS uuid[])))'),dict(tasks=tasks))])
        values['plugin_grants']=rows_sorted([row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_plugin_grants t WHERE installation_id IN (SELECT preferred_installation_id FROM agent_tasks WHERE task_id=ANY(CAST(:tasks AS uuid[])))'),dict(tasks=tasks))])
        values['model_deployments']=rows_sorted([row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_model_deployments t WHERE deployment_id IN (SELECT deployment_id FROM agent_task_model_bindings WHERE task_id=ANY(CAST(:tasks AS uuid[])))'),dict(tasks=tasks))])
        # Original proposal bodies are immutable; states legitimately change under staff decisions.
        values['proposal_bodies']=rows_sorted([dict(proposal_id=row[0],original_text=row[1]) for row in await db.execute(text(
            'SELECT proposal_id::text,original_text FROM capa_d5_proposals WHERE report_id=:id'),dict(id=identifier))])
        assert len(values['agent_d5_commands'])==2 and values['model_egress_audit']
        return values


async def verify(exercise):
    from sqlalchemy import text
    from app.database import tenant_async_session
    from tests.e2e.r6_exercise import write_private

    chain, prepared = FACTS['chain'], FACTS['prepared']
    d4, d5 = prepared['d4'], prepared['d5']
    d4_model, d5_model = FACTS['d4_model'], FACTS['d5_model']
    d4_task, task = d4_model['task'], chain['d5_task']
    candidates, workflow = d4_model['candidates'], d5_model['checkpoint']
    measure, root = MEASURE, exercise.root
    a_id, b_id = chain['a'], chain['b']
    ROOT_TEXT = chain['verification']['root_cause_text']
    ADOPTED_TEXT, CORRECTED_TEXT = chain['history']['adopted_text'], chain['history']['final_text']
    MANUAL_D5 = chain['manual_d5']
    lost = chain['adoption_loss']
    paths = ['', '/d4-candidates', '/root-cause-verifications', '/d5-proposals', '/d5-measures',
             '/local-closure', '/outcome-review', '/d5-measures/' + measure,
             '/d5-measures/' + measure + '/corrections', '/doc-gate/decision']
    exercise.allowed = {root + suffix for suffix in paths}
    current = await exercise.request('GET', root)
    assert current['status'] == 'D8_CLOSURE' and current['d4_root_cause'] == ROOT_TEXT
    assert current['d5_correction'] == MANUAL_D5 and current['d6_verification']
    verification = await exercise.request('GET', root + '/root-cause-verifications')
    assert len(verification) == 1 and verification[0]['conclusion'] == 'passed'
    assert verification[0]['verification_id'] == chain['verification']['verification_id']
    actual_candidates = (await exercise.request('GET', root + '/d4-candidates'))['items']
    assert {row['candidate_id'] for row in actual_candidates} == {row['candidate_id'] for row in candidates}
    confirmed = [row['body']['candidate_id'] for row in chain['database']['capa_d4_candidates'] if row['body']['state'] == 'adopted']
    assert len(confirmed) == 1
    assert {row['candidate_id'] for row in actual_candidates if row['state'] == 'adopted'} == set(confirmed)
    for name, enrollment in [('d4', d4), ('d5', d5)]:
        path = '/api/agent/tasks/' + chain[name + '_task']
        exercise.allowed.add(path)
        actual = await exercise.request('GET', path)
        assert actual['status'] == 'completed' and actual['target_capa_id'] == REPORT
        assert actual['preferred_installation_id'] == enrollment['installation_id']
        assert actual['model_deployment']['deployment_id'] == enrollment['model_deployment_id']
    proposals = (await exercise.request('GET', root + '/d5-proposals'))['items']
    assert {row['proposal_id']: row['state'] for row in proposals} == {a_id: 'adopted', b_id: 'withdrawn'}
    assert {row['proposal_id']: row['original_text'] for row in proposals} == {row['proposal_id']: row['original_text'] for row in d5_model['proposals']}
    a, b = [next(row for row in proposals if row['proposal_id'] == value) for value in (a_id, b_id)]
    measures = (await exercise.request('GET', root + '/d5-measures'))['items']
    assert len(measures) == 1 and measures[0]['measure_id'] == measure and measures[0]['proposal_id'] == a_id
    formal = await exercise.request('GET', root + '/d5-measures/' + measure)
    assert formal['adopted_text'] == ADOPTED_TEXT and formal['final_text'] == CORRECTED_TEXT
    assert formal['correction_revision_no'] == 1 and formal['can_correct'] is False
    history = await exercise.request('GET', root + '/d5-measures/' + measure + '/corrections')
    assert history == chain['history'] and len(history['corrections']) == 1
    source_evidence = {}
    for kind, identifier in [('d5-proposal', a_id), ('d5-proposal', b_id), ('d5-measure', measure)]:
        path = root + '/sources/' + kind + '/' + identifier
        exercise.allowed.add(path)
        source = await exercise.request('GET', path)
        assert source['proof']['state'] == 'active' and source['proof']['basis_current'] is True
        assert len(source['sources']) == 3
        assert {row['projection_id'] for row in source['sources']} == {
            'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'fmea.failure_cause.reference.v1'}
        assert all(row['current_state'] == 'current' for row in source['sources'])
        for item in source['sources']:
            evidence_path = path + '/evidence/' + item['source_id']
            exercise.allowed.add(evidence_path)
            body = await exercise.request('GET', evidence_path)
            assert body['current_state'] == 'current' and body['version'] == item['version']
        source_evidence[identifier] = source
    local = await exercise.request('GET', root + '/local-closure')
    assert local['prevention'] and local['manual_analysis']['candidates'] and local['propagation']
    decision = await exercise.request('GET', root + '/doc-gate/decision')
    assert decision['decision'] == 'passed' and decision['no_affected_confirmed'] is True
    approved = await exercise.request('GET', root + '/outcome-review', actor='approver')
    assert approved == chain['review']
    assert approved['binding_status'] == 'verified' and approved['contract'] == 'capa.outcome-review.v2'
    assert len(approved['local_closure']['propagation']['channels']) == 4
    assert set(approved['local_closure']['propagation']['channels'].values()) == {'NOT_EXECUTED'}
    export_row, = chain['database']['ppt_exports']
    export_path = root + '/ppt-exports/' + export_row['export_id']
    exercise.allowed.add(export_path)
    export = await exercise.request('GET', export_path)
    assert export['export_id'] == export_row['export_id'] and export['capa_id'] == REPORT
    ppt_bytes = (ORIGINAL / 'approved.pptx').read_bytes()
    with zipfile.ZipFile(io.BytesIO(ppt_bytes)) as package:
        slides = [ElementTree.fromstring(package.read(name)) for name in package.namelist()
                  if name.startswith('ppt/slides/slide') and name.endswith('.xml')]
    rendered = ''.join(node.text or '' for slide in slides for node in slide.iter(
        '{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
    assert CORRECTED_TEXT in rendered and MANUAL_D5 in rendered
    assert a['original_text'] not in rendered and b['original_text'] not in rendered
    before = await baseline(exercise)
    if PRIOR is not None:
        assert before == PRIOR['immutable_original_model']
    binding = exercise.binding()
    async with tenant_async_session(binding=binding) as db:
        evidence = {}
        for table, column in [('capa_r6_source_origins', 'report_id'), ('agent_d4_input_receipts', 'report_id'),
            ('capa_d4_candidates', 'report_id'), ('capa_d4_root_cause_source_proofs', 'report_id'),
            ('agent_d5_basis_receipts', 'report_id'), ('capa_d5_proposals', 'report_id'),
            ('capa_d5_measures', 'report_id')]:
            where = (f'{column}=:id' if table != 'capa_d5_measures' else
                'proposal_id IN (SELECT proposal_id FROM capa_d5_proposals WHERE report_id=:id)')
            evidence[table] = [dict(row) for row in (await db.execute(text(
                f'SELECT to_jsonb(t) AS body FROM {table} t WHERE {where}'),
                dict(id=UUID(exercise.data['report_id'])))).mappings()]
        origins = [row['body'] for row in evidence['capa_r6_source_origins']]
        assert len(origins) == 3
        assert {row['projection_id'] for row in origins} == {
            'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'fmea.failure_cause.reference.v1'}
        external = [row for row in origins if row['kind'] == 'fmea_projection']
        assert len(external) == 1 and external[0]['fmea_id'] == exercise.data['fmea_id']
        assert len(evidence['agent_d4_input_receipts']) >= 1
        assert {row['body']['source_count'] for row in evidence['agent_d4_input_receipts']} == {3}
        assert len(evidence['capa_d4_root_cause_source_proofs']) == 1
        assert len(evidence['capa_d5_measures']) == 1
        assert evidence['capa_d5_measures'][0]['body']['proposal_id'] == a['proposal_id']
        assert evidence['capa_d5_measures'][0]['body']['final_text'] == ADOPTED_TEXT
        proof = evidence['capa_d4_root_cause_source_proofs'][0]['body']
        assert proof['status'] == 'active' and proof['fmea_id'] == exercise.data['fmea_id'] and proof['cause_node_id'] == 'cause-a'
        root_sources = [str(row[0]) for row in await db.execute(text(
            'SELECT source_id FROM capa_r6_root_revision_sources WHERE revision_id=:id'), dict(id=UUID(proof['revision_id'])))]
        assert set(root_sources) == {item['source_id'] for item in origins}
        commands = [row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM agent_d5_commands t WHERE task_id=:task'), dict(task=UUID(task)))]
        assert len(commands) == 2
        watermark = await db.scalar(text('SELECT watermark FROM agent_d5_checkpoint_positions WHERE checkpoint_id=:id'),
            dict(id=UUID(workflow['checkpoint_id'])))
        assert all(row['sequence'] > watermark for row in commands)
        evidence['commands'] = commands
        evidence['checkpoint_watermark'] = watermark
        sidecars = [row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM capa_r6_root_delivery_bindings t WHERE report_id=:id'), dict(id=UUID(exercise.data['report_id'])))]
        snapshots = {item['source_id']: item for item in origins if item['kind'] == 'report_snapshot'}
        assert sidecars
        for sidecar in sidecars:
            assert sidecar['revision_id'] == proof['revision_id']
            inputs = sidecar['input_bindings']
            assert {item['source_id'] for item in inputs} == set(snapshots)
            for item in inputs:
                origin = snapshots[item['source_id']]
                assert item['snapshot_id'] == origin['snapshot_id'] and item['version'] == origin['version']
                assert item['projection_id'] == origin['projection_id'] and item['report_id'] == exercise.data['report_id']
                assert item['task_id'] == task and item['executor_id'] == exercise.data['actors']['qe']['user_id']
                assert item['installation_id'] == d5['installation_id'] and item['recipient_id'] == d5['model_deployment_id']
                assert item['external_source_id'] == external[0]['source_id']
        for receipt in evidence['agent_d5_basis_receipts']:
            assert receipt['body']['task_id'] == task and receipt['body']['proof_id'] == proof['proof_id']
            assert all(item['fmea_id'] == proof['fmea_id'] and item['node_id'] == proof['cause_node_id']
                and item['node_hmac'] == proof['node_hmac'] for item in receipt['body']['sources'])
        evidence['complete_root_delivery'] = sidecars
        required = {'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'capa.d4.root_cause_candidate.masked.v1', 'capa.d5.proposal.save.v1'}
        for table, key, identifier in [('agent_plugin_grants', 'installation_id', d5['installation_id']),
            ('agent_task_grants', 'task_id', task)]:
            grants = [row[0] for row in await db.execute(text(f'SELECT to_jsonb(t) FROM {table} t WHERE {key}=:id'), dict(id=UUID(identifier)))]
            assert {item['capability_id'] for item in grants} == required
            for item in grants:
                assert item['object_ids'] == [exercise.data['report_id']]
                assert item['factory_ids'] == [exercise.data['factory_id']]
                assert item['product_line_codes'] == [exercise.data['line']]
                if table == 'agent_plugin_grants':
                    assert item['enabled'] is True
            evidence[table] = grants
        for table in ['agent_plugin_derived_source_scopes', 'agent_task_derived_source_scopes']:
            scopes = [row[0] for row in await db.execute(text(f'SELECT to_jsonb(t) FROM {table} t WHERE target_report_id=:id'), dict(id=UUID(exercise.data['report_id'])))]
            assert scopes and all(item['fmea_id'] == proof['fmea_id'] and item['cause_node_id'] == proof['cause_node_id'] for item in scopes)
            evidence[table] = scopes
        ids = [exercise.data['report_id'], exercise.data['fmea_id'], measure, a['proposal_id'], b['proposal_id'],
            proof['proof_id'], proof['verification_id'], *[item['candidate_id'] for item in candidates]]
        audit = [row[0] for row in await db.execute(text(
            "SELECT to_jsonb(t) FROM audit_logs t WHERE record_id=ANY(CAST(:ids AS uuid[])) OR changed_fields->>'task_id'=ANY(CAST(:tasks AS text[]))"),
            dict(ids=[UUID(item) for item in ids], tasks=[task, d4_task['task_id']]))]
        actions = {row['action'] for row in audit}
        assert {'CONFIRM_D4_CANDIDATE', 'D4_VERIFICATION_PASSED', 'D4_SOURCE_PROOF_ISSUED',
            'CORRECT_D5_MEASURE', 'R6_PROPAGATION_NOT_EXECUTED', 'MODEL_EGRESS_COMPLETED'} <= actions
        evidence['audit'] = audit
        staff = [row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM capa_d5_staff_receipts t WHERE proposal_id=:id AND operation=:operation'),
            dict(id=UUID(a['proposal_id']), operation='adopt'))]
        assert len(staff) == 1 and staff[0]['operation_key'] == lost['command']['operation_key']
        assert staff[0]['actor_id'] == exercise.data['actors']['colleague']['user_id'] and staff[0]['measure_id'] == measure
        adoption_audits = [item for item in audit if item['record_id'] == a['proposal_id'] and item['action'] == 'D5_PROPOSAL_ADOPT']
        assert len(adoption_audits) == 1
        evidence['adoption_decision'] = staff
        evidence['correction_revisions'] = [row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM capa_d5_measure_revisions t WHERE measure_id=:id'), dict(id=UUID(measure)))]
        assert len(evidence['correction_revisions']) == 1
        evidence['ppt_exports'] = [row[0] for row in await db.execute(text(
            'SELECT to_jsonb(t) FROM capa_ppt_export t WHERE capa_id=:id'), dict(id=UUID(exercise.data['report_id'])))]
        assert len(evidence['ppt_exports']) == 1
        for table in ['capa_lessons_learned', 'supplier_risk_capa_inputs']:
            assert await db.scalar(text(f'SELECT count(*) FROM {table} WHERE capa_id=:id'), dict(id=UUID(exercise.data['report_id']))) == 0
        assert await db.scalar(text('SELECT count(*) FROM knowledge_entries WHERE source_id=:id'),
            dict(id=UUID(exercise.data['report_id']))) == 0
        assert await db.scalar(text('SELECT count(*) FROM capa_lateral_diffusion_checks WHERE capa_id=:id'),
            dict(id=UUID(exercise.data['report_id']))) == 0
        mes = [row[0] for row in await db.execute(text('SELECT payload FROM mes_push_outbox WHERE payload->>\'capa_id\'=:id'),
            dict(id=exercise.data['report_id']))]
        from datetime import datetime
        from app.state_machines.eightd_state import EightDState
        states={state.value for state in EightDState}
        assert mes
        for item in mes:
            assert set(item)=={'capa_id','old_status','new_status','changed_at','product_line_code'}
            assert UUID(item['capa_id'])==UUID(exercise.data['report_id'])
            assert item['product_line_code']==exercise.data['line']
            assert item['old_status'] in states and item['new_status'] in states
            changed=datetime.fromisoformat(item['changed_at'])
            assert changed.tzinfo is not None and changed.utcoffset() is not None
        evidence['mes_status_events'] = mes  # IDs/status/routing/time; never business body.
    after = await baseline(exercise)
    assert after == before and not exercise.violations
    snapshot = dict(evidence_method=('FRESH_SINGLE_PASS' if chain['live_provider'] else 'CONTROLLED_READONLY_WALKTHROUGH'),
        live_provider=chain['live_provider'],
        report_id=REPORT, current=current, d4_task=d4_task['task_id'], d5_task=task,
        a=a_id, b=b_id, measure_id=measure, verification=verification, history=history,
        local=local, decision=decision, review=approved, current_sources=source_evidence,
        existing_export=export, saved_ppt_sha256=hashlib.sha256(ppt_bytes).hexdigest(),
        adoption_loss=lost, adoption_replay=chain['adoption_replay'], database=evidence,
        immutable_original_model=before, immutable_model_before=before, immutable_model_after=after,
        new_model_calls=0, original_switch=chain['switch'], receipts=exercise.receipts)
    if PRIOR is not None:
        for key in ('current', 'history', 'review', 'local', 'decision', 'current_sources', 'saved_ppt_sha256'):
            assert snapshot[key] == PRIOR[key]
    write_private(exercise.output / 'c9-evidence.json', snapshot)
    return snapshot
