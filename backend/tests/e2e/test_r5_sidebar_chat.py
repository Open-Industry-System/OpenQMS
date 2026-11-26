"""Employee task dialogue through Chromium, the managed worker and a loopback model."""
import json

import pytest
from sqlalchemy import select

from app.api import fmea, knowledge, product_line
from app.models.agent_task import AgentTaskMessage
from app.models.capa_d5_proposal import CapaD5Proposal
from tests.e2e.agent_local_trial_harness import PASSWORD
from tests.e2e.d4_text_local_harness import d4_text_local_trial, owned_local_trial
from tests.e2e.test_r5_d5_ui import run_r5_browser
from tests.e2e.test_r5_model_agent import actual_agent, call, scripted_model
from tests.services.agent_runtime.test_r5_model_binding import r5_case

pytestmark = [pytest.mark.ci_r5_native, pytest.mark.requires_db, pytest.mark.ci_browser]


@pytest.mark.asyncio
async def test_employee_continues_r5_sidebar_conversation_on_desktop_and_narrow_screen(r5_case, tmp_path):
    c = r5_case
    for router in (product_line.router, fmea.router, knowledge.router):
        c.app.include_router(router)
    await actual_agent(c)
    proposal_text = '为此工序增加首件复核，并记录复核结果。'
    questions = ['还有需要核对的额外资料吗？', '夜班也执行同样的检查吗？']
    replies = ['{"intent":"continue_d5","additional_context":"none"}', '夜班也会在首件时执行检查。']
    # Ask before delivering D4 so the later question creates the round's sole checkpoint.
    scripted_model(c, [
        call('request_supplement', {'question': questions[0]}, 'ask-desktop'),
        call('read_d4'),
        call('save_proposal', {'text': proposal_text}, 'save'),
        call('request_supplement', {'question': questions[1]}, 'ask-narrow'),
        {'content': '已记录夜班的检查安排。'},
    ])
    await run_r5_browser(c, tmp_path, 'r5-sidebar-chat.spec.ts', {
        'AGENT_BROWSER_LOGIN': json.dumps({
            'username': 'trial-executor',
            'password': PASSWORD,
            'installation': str(c.r5_id),
            'model': c.create_body['model_deployment_id'],
            'proposal': proposal_text,
            'questions': questions,
            'replies': replies,
        }),
    })
    async with c.session() as db:
        proposal = (await db.scalars(select(CapaD5Proposal))).one()
        assert proposal.original_text == proposal_text
        assert proposal.state == 'pending'
        messages = list(await db.scalars(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == proposal.task_id,
        ).order_by(AgentTaskMessage.sequence)))
        assert [message.content for message in messages] == [c.create_body['initial_text'], *replies]
        assert all(message.state == 'accepted' for message in messages)
    assert len(c.witness.a.bodies) == 5
    assert c.witness.b.bodies == []
    received_replies = [c.witness.a.bodies[1], c.witness.a.bodies[4]]
    for turn, reply in zip(received_replies, replies, strict=True):
        assert any(message['role'] == 'user' and reply in message['content'] for message in turn['messages'])
