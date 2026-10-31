"""Positive acceptance uses actual employee HTTP and real business/provider services."""
import os


async def business_response(client, method, path, payload=None, expected=200):
    """Actual failure body; controlled runner redacts test-provider credentials."""
    response = await client.request(method, path, json=payload)
    assert response.status_code == expected, f'{method} {path}: HTTP {response.status_code}; {response.text}'
    return response.json()


def displayed_expectation(review):
    return {'expected_outcome_revision': review['revision'], 'expected_review_round_id': review['review_round_id']}


async def submit_real_document_gate(editor, path, *, owned=None, sources=None):
    """Never replace provider output or decisions, including a real empty allowlist."""
    impact = await business_response(editor, 'POST', path + '/doc-gate/impact', {})
    assert impact['status'] == 'done', f'D8 document impact failed: {impact}'
    actual = await business_response(editor, 'GET', path + '/doc-gate/impact')
    if sources is None:
        assert actual['affected_docs'] == [], 'Unexpected document scope; do not manufacture coverage'
        decision = await business_response(editor, 'POST', path + '/doc-gate/confirm-no-affected', {})
        assert decision == {'decision': 'passed', 'no_affected_confirmed': True}
    else:
        assert {doc['doc_id'] for doc in actual['affected_docs']} == set(sources.values()), (
            'Live provider did not identify both synthetic controlled documents; acceptance not verified')
        # These documents have no baseline version. Their actual first publication
        # is the business document-add operation; do not synthesize snapshots/audits.
        for doc in actual['affected_docs']:
            assert all(kp['target_kind'] == 'document' and kp['expected_action'] == 'add' for kp in doc['key_points'])
        async with owned.client() as publisher:
            await business_response(publisher, 'POST', f"/api/fmea/{sources['fmea_id']}/transition", {'target_status': 'in_review'})
            await business_response(publisher, 'POST', f"/api/control-plans/{sources['cp_id']}/approve", {})
        audit = await business_response(editor, 'POST', path + '/doc-gate/audit', {})
        assert audit['decision'] == 'passed', f'Actual document audit did not pass: {audit}'
    result = await business_response(editor, 'POST', path + '/advance', {'target_state': 'D8_APPROVAL_PENDING'})
    assert result['capa']['status'] == 'D8_APPROVAL_PENDING'


async def progress_real_outcome(owned, *, sources=None):
    """All positive states arise over HTTP, including D3/D4/D7/D8 gates."""
    assert os.environ.get('OPENQMS_OUTCOME_LIVE_TEST') == '1', 'Live test-provider opt-in required'
    path = f'/api/capa/{owned.report_id}'
    async with owned.client('editor') as editor:
        await business_response(editor, 'PUT', path, {'d1_team': [{'name': '合成工程师', 'role': '质量'}],
            'd2_description': '合成产品扭矩不足，复现实验样件，不含真实客户资料。',
            'd3_interim': '合成样件已隔离并完成复测。'})
        for target in ('D2_DESCRIPTION', 'D3_INTERIM'):
            await business_response(editor, 'POST', path + '/advance', {'target_state': target})
        imported = await business_response(editor, 'POST', path + '/d3/import', {})
        assert imported['report_status'] == 'done', (
            f"LIVE_PROVIDER_BLOCKED: config={os.environ.get('OPENQMS_OUTCOME_PROVIDER_CONFIG')}; "
            f"D3 report_status={imported['report_status']}; report_error={imported['report_error']}")
        await business_response(editor, 'POST', path + '/d3/execution', {'source': 'manual',
            'measure_text': '合成样件已隔离，复测记录已确认。', 'result_status': 'completed',
            'evidence_refs': [{'name': 'synthetic containment fixture data',
                'url': './fixtures/capa-outcome-containment.txt'}]})
        await business_response(editor, 'POST', path + '/advance', {'target_state': 'D4_ROOT_CAUSE'})
        await business_response(editor, 'PUT', path, {'d4_root_cause': '合成样件扭矩不足'})
        response = await editor.post(path + '/advance', json={'target_state': 'D5_CORRECTION'})
        assert response.status_code == 400
        verification = await business_response(editor, 'POST', path + '/root-cause-verifications', {
            'root_cause_text': '合成样件扭矩不足', 'method': 'measurement', 'conclusion': 'passed',
            'result': '合成扭矩实验确认根因', 'evidence_attachments': [{'name': 'synthetic torque worksheet'}]})
        await business_response(editor, 'POST', path + '/advance', {'target_state': 'D5_CORRECTION'})
        await business_response(editor, 'PUT', path, {'d5_correction': '已更换合成工装扭矩控制工具并执行点检。'})
        await business_response(editor, 'POST', path + '/advance', {'target_state': 'D6_VERIFICATION'})
        await business_response(editor, 'PUT', path, {'d6_verification': '实施后复测合格'})
        await business_response(editor, 'POST', path + '/advance', {'target_state': 'D7_PREVENTION'})
        await business_response(editor, 'PUT', path, {'d7_prevention': '已更新合成工装点检要求并培训。'})
        await complete_real_d7(editor, path)
        await submit_real_document_gate(editor, path, owned=owned, sources=sources)
    return verification['verification_id']


async def prepare_real_documents(owned):
    """Synthetic new controlled documents, over real employee endpoints only."""
    async with owned.client() as client:
        fmea = await business_response(client, 'POST', '/api/fmea', {
            'title': '合成工装扭矩不足的预防控制 FMEA（新文件）', 'document_no': 'PFMEA-OUTCOME-LIVE',
            'product_line_code': 'OUTCOME-LIVE', 'fmea_type': 'PFMEA'}, expected=201)
        fmea_id = fmea['fmea_id']
        await business_response(client, 'PUT', f'/api/fmea/{fmea_id}', {'graph_data': {
            'nodes': [{'id': 'fm-owned', 'type': 'FailureMode', 'name': '合成样件扭矩不足'},
                {'id': 'cause-owned', 'type': 'FailureCause', 'name': '合成样件扭矩不足'},
                {'id': 'pc-owned', 'type': 'PreventionControl', 'name': '更换扭矩工具并完成点检'}],
            'edges': [{'source': 'cause-owned', 'target': 'fm-owned', 'type': 'CAUSE_OF'},
                {'source': 'cause-owned', 'target': 'pc-owned', 'type': 'PREVENTED_BY'}],
            'wizardScope': {'wizard_completed': True}}})
        cp = await business_response(client, 'POST', '/api/control-plans', {
            'title': '合成工装扭矩复测及点检控制计划（新文件）', 'document_no': 'CP-OUTCOME-LIVE',
            'fmea_ref_id': fmea_id, 'product_line_code': 'OUTCOME-LIVE'}, expected=201)
        await business_response(client, 'PUT', f"/api/control-plans/{cp['cp_id']}", {'items': [{
            'step_no': 'OP10', 'process_name': '合成工装装配', 'process_characteristic': '扭矩',
            'control_method': '更换扭矩工具并点检', 'reaction_plan': '隔离合成样件并复测',
            'sample_frequency': '每批合成样件', 'sample_size': '3', 'source_fmea_node_id': 'fm-owned'}]})
        await business_response(client, 'POST', f'/api/capa/{owned.report_id}/link-fmea?fmea_id={fmea_id}', {})
    return {'fmea_id': fmea_id, 'cp_id': cp['cp_id']}



async def complete_real_d7(editor, path):
    recommendations = await business_response(editor, 'GET', path + '/d7-fmea-recommendations')
    for rec in recommendations['recommendations']:
        await business_response(editor, 'POST', path + '/d7-node-actions', {
            'action': 'skipped', 'fmea_id': rec['fmea_id'],
            'failure_mode_node_id': rec['failure_mode_node_id'],
            'failure_cause_node_id': rec.get('failure_cause_node_id'), 'match_source': rec['match_source'],
            'reason': '合成试验产品线，无适用量产文件；措施已实施并留复测结果。'})
    for target in ('D7_COMPLETED', 'D8_GATE_PENDING'):
        await business_response(editor, 'POST', path + '/advance', {'target_state': target})


async def exercise_real_pending_http(owned, verification_id):
    """Negative decisions before browser approval; never seed a pending gate/round."""
    path = f'/api/capa/{owned.report_id}'
    async with owned.client('editor') as editor, owned.client() as approver:
        seen = await business_response(approver, 'GET', path + '/outcome-review')
        before = await owned.snapshot()
        denied = await editor.post(path + '/advance', json={'target_state': 'D8_CLOSURE', **displayed_expectation(seen)})
        assert denied.status_code == 403
        assert await owned.snapshot() == before
        for suffix, method, data in [('', 'PUT', {'d6_verification': '实施后新增复测记录'}),
                (f'/root-cause-verifications/{verification_id}', 'PATCH', {'result': '新增合成验证结论'})]:
            seen = await business_response(approver, 'GET', path + '/outcome-review')
            await business_response(editor, method, path + suffix, data)
            before = await owned.snapshot()
            conflict = await approver.post(path + '/advance', json={'target_state': 'D8_CLOSURE', **displayed_expectation(seen)})
            assert conflict.status_code == 409
            assert conflict.json() == {'detail': 'CAPA_OUTCOME_REVIEW_CHANGED'}
            assert await owned.snapshot() == before
        await business_response(editor, 'PUT', path, {'d6_verification': '实施后复测合格'})
        seen = await business_response(approver, 'GET', path + '/outcome-review')
        before = await owned.snapshot()
        empty = await approver.post(path + '/advance', json={'target_state': 'D7_PREVENTION',
            'reject_reason': '   ', **displayed_expectation(seen)})
        assert empty.status_code == 400
        assert await owned.snapshot() == before
        rejected = await business_response(approver, 'POST', path + '/advance', {
            'target_state': 'D7_PREVENTION', 'reject_reason': '需补足合成复测证据', **displayed_expectation(seen)})
        assert rejected['capa']['status'] == 'D7_PREVENTION'
        await business_response(editor, 'PUT', path, {'d6_verification': '实施后复测合格'})
        await complete_real_d7(editor, path)
        await submit_real_document_gate(editor, path)
        current = await business_response(approver, 'GET', path + '/outcome-review')
        assert current['review_round_id'] != seen['review_round_id']
        before = await owned.snapshot()
        stale = await approver.post(path + '/advance', json={'target_state': 'D8_CLOSURE', **displayed_expectation(seen)})
        assert stale.status_code == 409
        assert stale.json() == {'detail': 'CAPA_OUTCOME_REVIEW_CHANGED'}
        assert await owned.snapshot() == before
