"""C9: one preserved synthetic 8D, real Terra, employees and Chromium.

The registered owner environment must be provisioned explicitly. This test is
intentionally fail closed rather than skipping an unavailable live resource.
"""
import asyncio
import json
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.e2e.r6_exercise import Exercise, write_private

ROOT_TEXT = '定位销磨损且未执行现行开班检查，导致本合成批次孔径超差；候选经员工核对，现场效果另行验证。'
ADOPTED_TEXT = '按现行控制执行定位销检查和磨损件更换，记录检查结果。'
CORRECTED_TEXT = '由合成员工C9-QE执行现行开班定位销检查，磨损件按既有要求更换，并在既有点检表记录执行人和结果；频次、阈值及文件要求不变。'
MANUAL_D5 = '按既有流程复核合成批次隔离和点检记录，保留人工纠正说明；此普通手工正文与独立正式措施并存。'


async def prepare(exercise, *, live=True):
    await exercise.start(live=live)
    source = await exercise.request('GET', '/api/fmea/' + exercise.data['fmea_id'])
    # The normal employee saves and submits a genuine synthetic document. No
    # seeded approval, passed impact analysis or forced no-affected decision.
    graph = dict(nodes=[dict(id='cause-a', type='FailureCause',
        name='定位销磨损导致孔径超差；现行控制要求开班检查定位销并更换磨损件，记录执行人和结果。本次漏执行既有检查。')],
        edges=[], wizardScope=dict(wizard_completed=True))
    await exercise.request('PUT', '/api/fmea/' + exercise.data['fmea_id'],
        dict(lock_version=source['lock_version'], graph_data=graph))
    for status in ['in_review', 'approved']:
        await exercise.request('POST', '/api/fmea/' + exercise.data['fmea_id'] + '/transition',
            dict(target_status=status, reason='合成既有点检控制基线；正常员工审阅批准'), actor='approver')
    d4 = await exercise.enroll('model_d4_candidate_v1', 'c9-d4-20261117', live=live)
    d5 = await exercise.enroll('model_d5_proposal_r6_v1', 'c9-d5-20261117', live=live)
    await exercise.activate(d4, live=live)
    await exercise.switch([d4, d5])
    write_private(exercise.directory / 'prepared.json', dict(d4=d4, d5=d5, receipts=exercise.receipts))
    return d4, d5


async def run_chain(exercise, *, live=True, semantic_review=None):
    # A failed attempt is retained. A model call is never blindly repeated
    # against partially completed business work by rerunning this test.
    if (exercise.directory / 'live-attempt.json').exists():
        raise AssertionError('preserved live attempt exists; inspect and explicitly resume it')
    prepared = exercise.directory / 'prepared.json'
    if prepared.exists():
        enrolled = json.loads(prepared.read_text())
        d4, d5 = enrolled['d4'], enrolled['d5']
        await exercise.activate(d4, live=live)
    else:
        d4, d5 = await prepare(exercise, live=live)
    detail = await exercise.request('GET', exercise.root)
    assert not detail['d4_root_cause']
    assert await exercise.request('GET', exercise.root + '/root-cause-verifications') == []
    write_private(exercise.directory / 'live-attempt.json', dict(stage='before-first-model', live=live, report_id=exercise.data['report_id']))
    await exercise.browser('generate-d4', installation=d4['installation_id'], deployment=d4['model_deployment_id'])
    d4_entry=json.loads((exercise.directory/'playwright-generate-d4/task-entry.json').read_text())
    d4_task,launched=d4_entry['creation']['task'],d4_entry['launch']['body']
    d4_entry['completion']=await exercise.request('GET',f"/api/agent/tasks/{d4_task['task_id']}")
    assert d4_entry['completion']['status']=='completed'
    candidates = (await exercise.request('GET', exercise.root + '/d4-candidates'))['items']
    assert candidates, 'real model must persist a D4 candidate'
    assert all(item['state'] == 'pending' for item in candidates)
    assert not (await exercise.request('GET', exercise.root))['d4_root_cause']
    assert await exercise.request('GET', exercise.root + '/root-cause-verifications') == []
    write_private(exercise.directory / 'd4-model.json', dict(task=d4_task, launch=launched, candidates=candidates))
    await exercise.browser('view-candidate', actor='view', candidate=candidates[0]['candidate_id'])
    context = await exercise.request('GET', exercise.root + f"/d4-candidates/{candidates[0]['candidate_id']}/confirmation-context", actor='view')
    await exercise.request('POST', exercise.root + f"/d4-candidates/{candidates[0]['candidate_id']}/confirm", dict(
        operation_key='view-denied', expected_material_version=context['material_version'],
        expected_candidate_version=context['candidate_version'], final_text=ROOT_TEXT), actor='view', expected=403)
    await exercise.browser('confirm', candidate=candidates[0]['candidate_id'], final_text=ROOT_TEXT)
    verification = await exercise.request('POST', exercise.root + '/root-cause-verifications', dict(
        root_cause_text=ROOT_TEXT, method='measurement', conclusion='passed',
        result='合成现场验证事实由员工独立签录：原定位销磨损且开班记录漏填；更换磨损件并执行既有点检后，同一工艺窗口复测200件0件超差。该记录不是模型证明。',
        source_ref=dict(fmea_id=exercise.data['fmea_id'], cause_node_id='cause-a'),
        source_declaration=dict(declares_complete_coverage=True)))
    assert verification['source_proof_issued'] is True
    await exercise.request('POST', exercise.root + '/advance', {})
    await exercise.activate(d5, live=live)
    await exercise.browser('generate-d5', installation=d5['installation_id'], deployment=d5['model_deployment_id'])
    d5_entry=json.loads((exercise.directory/'playwright-generate-d5/task-entry.json').read_text())
    d5_task=d5_entry['creation']['task']
    task = d5_task['task_id']
    d5_entry['completion']=await exercise.request('GET',f'/api/agent/tasks/{task}')
    assert d5_entry['completion']['status']=='completed'
    workflow=d5_entry['checkpoint']
    assert workflow['checkpoint_id'] and d5_entry['proposals_before_continue']['items']==[]
    proposals = (await exercise.request('GET', exercise.root + '/d5-proposals'))['items']
    assert len(proposals) == 2 and {p['state'] for p in proposals} == {'pending'}
    assert {p['task_id'] for p in proposals} == {task}
    write_private(exercise.directory / 'd5-model.json', dict(task=d5_task, checkpoint=workflow, proposals=proposals))
    # The employee checks actual generated meaning before adopting wording
    # and claiming no document impact. A desired constant cannot silently
    # turn an arbitrary model recommendation into a no-affected result.
    review_path = exercise.directory / 'employee-d5-review.json'
    if semantic_review is not None:
        write_private(review_path, semantic_review(exercise, task, proposals))
    # Bounded nominal 1800s for an actual employee semantic decision; this
    # does not change model/application budgets or accept proposals automatically.
    for _ in range(36000):
        if review_path.exists():
            break
        await asyncio.sleep(.05)
    else:
        raise AssertionError('actual generated proposals require employee semantic review')
    employee_review = json.loads(review_path.read_text())
    assert employee_review['report_id'] == exercise.data['report_id']
    assert employee_review['task_id'] == task and employee_review['reviewed_existing_control'] is True
    assert employee_review['reason'].strip()
    a = next(item for item in proposals if item['proposal_id'] == employee_review['selected_proposal_id'])
    b = next(item for item in proposals if item['proposal_id'] != a['proposal_id'])
    await exercise.browser('adopt', actor='colleague', proposal=a['proposal_id'],
        other_proposal=b['proposal_id'], adopted_text=ADOPTED_TEXT)
    lost = json.loads((exercise.directory / 'playwright-adopt/adoption-response-loss.json').read_text())
    replayed = await exercise.request('POST', exercise.root + f"/d5-proposals/{a['proposal_id']}/adopt",
        lost['command'], actor='colleague')
    assert replayed == lost['result']
    measures = (await exercise.request('GET', exercise.root + '/d5-measures'))['items']
    assert len(measures) == 1
    measure = measures[0]['measure_id']
    assert measures[0]['proposal_id'] == a['proposal_id'] and measure == replayed['measure_id']
    current = await exercise.request('GET', exercise.root)
    await exercise.browser('manual', manual_text=MANUAL_D5, adopted_text=ADOPTED_TEXT, entry_epoch=current['entry_epoch'])
    assert (await exercise.request('GET', exercise.root))['d5_correction'] == MANUAL_D5
    await exercise.browser('correct', actor='colleague', measure=measure, final_text=CORRECTED_TEXT, adopted_text=ADOPTED_TEXT)
    await exercise.browser('withdraw', task=task, checkpoint=workflow['checkpoint_id'],
        withdrawn=b['proposal_id'], final_text=CORRECTED_TEXT)
    withdrawal = await exercise.request('POST', f"/api/agent/tasks/{task}/d5-checkpoints/{workflow['checkpoint_id']}/proposals/withdraw",
        dict(operation_key='c9-withdraw-after-checkpoint', reason='员工保留已采纳A并撤回未采用B；含过期A选择逐项核对',
            proposal_ids=[a['proposal_id'], b['proposal_id']]))
    assert [item['outcome'] for item in withdrawal] == ['adopted', 'withdrawn']
    history = await exercise.request('GET', exercise.root + f'/d5-measures/{measure}/corrections')
    assert history['adopted_text'] == ADOPTED_TEXT
    assert len(history['corrections']) == 1 and history['final_text'] == CORRECTED_TEXT
    assert history['corrections'][0]['revision_no'] == 1
    assert history['corrections'][0]['final_text'] == CORRECTED_TEXT
    assert history['adopted_by'] == exercise.data['actors']['colleague']['user_id']
    refreshed = (await exercise.request('GET', exercise.root + '/d5-proposals'))['items']
    assert {item['proposal_id']: item['state'] for item in refreshed} == {a['proposal_id']: 'adopted', b['proposal_id']: 'withdrawn'}
    assert {item['proposal_id']: item['original_text'] for item in refreshed} == {
        a['proposal_id']: a['original_text'], b['proposal_id']: b['original_text']}
    await exercise.browser('local-close', impact_reason=employee_review['reason'])
    form = await exercise.request('GET', exercise.root + '/local-closure')
    assert form['manual_analysis']['candidates']
    review = await exercise.request('GET', exercise.root + '/outcome-review', actor='approver')
    assert review['core']['d5_correction'] == MANUAL_D5
    assert len(review['d5_measures']) == 1
    assert review['d5_measures'][0]['measure_id'] == measure and review['d5_measures'][0]['final_text'] == CORRECTED_TEXT
    assert review['d5_measures'][0]['correction_revision_id'] == history['correction_revision_id']
    assert review['d5_measures'][0]['correction_revision_no'] == history['correction_revision_no'] == 1
    assert len(review['d5_measures'][0]['text_version']) == 64
    assert review['contract'] == 'capa.outcome-review.v2'
    assert set(review['local_closure']['propagation']['channels'].values()) == {'NOT_EXECUTED'}
    await exercise.browser('approve', actor='approver', manual_text=MANUAL_D5, final_text=CORRECTED_TEXT,
        adopted_text=ADOPTED_TEXT, measure=measure, withdrawn=b['proposal_id'])
    approved = await exercise.request('GET', exercise.root + '/outcome-review', actor='approver')
    assert approved['binding_status'] == 'verified' and approved['revision'] == review['revision']
    await exercise.browser('closed', measure=measure, final_text=CORRECTED_TEXT, manual_text=MANUAL_D5, withdrawn=b['proposal_id'])
    import io
    import zipfile
    from xml.etree import ElementTree
    ppt_bytes = (exercise.directory / 'playwright-closed/approved.pptx').read_bytes()
    with zipfile.ZipFile(io.BytesIO(ppt_bytes)) as package:
        slides = [ElementTree.fromstring(package.read(name)) for name in package.namelist()
            if name.startswith('ppt/slides/slide') and name.endswith('.xml')]
    rendered_text = ''.join(node.text or '' for slide in slides for node in slide.iter(
        '{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
    assert CORRECTED_TEXT in rendered_text and MANUAL_D5 in rendered_text
    assert a['original_text'] not in rendered_text and b['original_text'] not in rendered_text
    (exercise.directory / 'approved.pptx').write_bytes(ppt_bytes)
    from app.core.tenant_transaction import TenantBinding
    from app.database import tenant_async_session
    binding = TenantBinding(UUID(exercise.data['tenant_id']), exercise.data['schema'], exercise.data['generation'], 'business')
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
    write_private(exercise.directory / 'c9-evidence.json', dict(live_provider=live, report_id=exercise.data['report_id'], d4_task=d4_task['task_id'],
        d5_task=task, measure_id=measure, a=a['proposal_id'], b=b['proposal_id'], history=history,
        verification=verification, withdrawal=withdrawal, review=approved, manual_d5=MANUAL_D5,
        adoption_loss=lost, adoption_replay=replayed, database=evidence, receipts=exercise.receipts,
        switch=json.loads((exercise.directory / 'build-and-switch.json').read_text()),
        browser_model_entries=dict(d4=d4_entry,d5=d5_entry)))
    write_private(exercise.directory / 'live-attempt.json', dict(stage='approved-and-preserved', report_id=exercise.data['report_id']))


@pytest.mark.requires_db
@pytest.mark.live_provider
@pytest.mark.asyncio
async def test_real_terra_empty_root_through_corrected_local_approval():
    async with Exercise() as exercise:
        await run_chain(exercise)
