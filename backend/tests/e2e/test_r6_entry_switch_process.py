"""Controlled recipients prove rejection and source delivery before cloud use.

These native tests use the owned TCP harness, not the real-cloud C9 receipt.
"""
import pytest

from tests.capa.test_r6_d4_confirm import (
    d4_case, r5_case, d4_text_local_trial, owned_local_trial, _managed_claim,
    _generate_and_confirm, _verify, _profile,
)

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.asyncio]


async def test_c9_controlled_empty_root_to_current_single_source_delivery(d4_case):
    c = d4_case
    from app.api.capa_r6 import router
    c.app.include_router(router)
    await _generate_and_confirm(c, 'c9-controlled-d4', '定位销磨损导致孔径超差')
    await _verify(c, '定位销磨损导致孔径超差')
    await _profile(c, 'model_d5_proposal_r6_v1', 'c9-controlled', c.source_scope)
    await _managed_claim(c)
    c.witness.a.bodies.clear()
    response = await c.client.post('/api/agent/runtime/model/infer', json={},
        headers={'Authorization': 'Bearer ' + c.token})
    assert response.status_code == 200, response.text
    assert len(c.witness.a.bodies) == 1 and not c.witness.b.bodies


async def test_c9_controlled_extra_external_source_stops_before_provider(d4_case):
    # Same genuine delivered-input construction as the main chain, then a
    # second independently captured source on this separate disposable report.
    from tests.capa.test_r6_d4_confirm import test_extra_external_origin_never_leaves_server
    await test_extra_external_origin_never_leaves_server(d4_case)


async def _fixed_prompt(c):
    from tests.e2e.test_r5_model_agent import actual_agent, scripted_model
    await actual_agent(c)
    scripted_model(c, [{'content': 'done'}])
    created = await c.client.post('/api/agent/tasks', json=c.create_body)
    assert created.status_code == 201, created.text
    launched = await c.client.post('/api/agent/tasks/' + created.json()['task_id'] + '/launch', timeout=130)
    assert launched.status_code == 200, launched.text
    assert len(c.witness.a.bodies) == 1 and not c.witness.b.bodies
    return next(m['content'] for m in c.witness.a.bodies[0]['messages'] if m['role'] == 'user')


async def test_fixed_start_keeps_r5_prompt_exactly_unchanged(r5_case):
    prompt = await _fixed_prompt(r5_case)
    assert prompt == ('deliver_d4_root_cause_candidate_v1\nEmployee request: Using only the current authorized D4 root cause '
        'and its source evidence, generate actionable D5 corrective-measure proposals '
        'and save suitable proposals to this report using save_proposal for employee review. '
        'Plan the steps yourself and ask for clarification when needed. '
        'Saved proposals require separate employee adoption.')


async def test_r6_fixed_start_plans_checkpoint_and_two_source_bound_proposals(d4_case):
    c = d4_case
    from app.api.capa_r6 import router
    c.app.include_router(router)
    await _generate_and_confirm(c, 'c9-prompt', '定位销磨损导致孔径超差')
    await _verify(c, '定位销磨损导致孔径超差')
    await _profile(c, 'model_d5_proposal_r6_v1', 'c9-prompt', c.source_scope)
    c.witness.a.bodies.clear()
    prompt = await _fixed_prompt(c)
    assert 'request_supplement' in prompt, 'R6 fixed start lacks pre-save employee checkpoint planning'
    assert 'exactly two' in prompt, 'R6 fixed start lacks two independently reviewable proposals'
    assert 'additional_context' in prompt and 'none' in prompt
