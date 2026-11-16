import pytest
from tests.services.agent_runtime.test_r5_model_binding import r5_case, d4_text_local_trial, owned_local_trial
pytestmark=[pytest.mark.requires_db,pytest.mark.ci_r5_native]

@pytest.mark.asyncio
async def test_employee_deployment_profile_is_verified_readonly_metadata(r5_case):
    c=r5_case
    response=await c.client.get('/api/agent/models')
    assert response.status_code==200,response.text
    assert response.json()['items'][0]['profile']=='model_d5_proposal_v1'
    assert set(response.json()['items'][0])=={'deployment_id','name','version','kind','profile'}
