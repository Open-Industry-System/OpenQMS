"""Real numeric-loopback SDK candidate command; no backend imports or DNS."""
import json
from datetime import datetime,timedelta,timezone
from uuid import UUID

from openqms_agent_sdk import ManagedLaunch,RunClient


def test_managed_candidate_command_runs_through_real_transport_and_codec(serve):
    run,task,candidate,command,report=[UUID(int=i) for i in range(1,6)]
    payload=json.dumps(dict(run_id=str(run),task_id=str(task),candidate_id=str(candidate),
        command_id=str(command),report_id=str(report),state='pending',version=1)).encode()
    wire=(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '
        +str(len(payload)).encode()+b'\r\n\r\n'+payload)
    origin,requests=serve([(0,wire)])
    launch=ManagedLaunch.from_dict(dict(protocol='r6.d4.launch.v1',profile='model_d4_candidate_v1',api_origin=origin,
        tenant_slug='fixture',token='synthetic-opaque',run_id=str(run),task_id=str(task),deployment_id=str(UUID(int=9)),
        lease_epoch=1,lease_expires_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),accepted_message_seq=0,has_resume_checkpoint=False))
    with RunClient.from_launch(launch) as client:
        result=client.save_d4_candidate(command_key='safe',text='hypothesis',supporting=('D2',))
    assert result.candidate_id==candidate
    assert len(requests)==1 and requests[0].startswith(b'POST /api/agent/runtime/capa/d4/candidates HTTP/1.1')
    assert b'X-OpenQMS-Task: '+str(task).encode() in requests[0]
    assert b'X-OpenQMS-Run: '+str(run).encode() in requests[0]
    assert b'X-OpenQMS-Lease: 1' in requests[0]
    assert b'X-OpenQMS-Deployment: '+str(UUID(int=9)).encode() in requests[0]
    body=json.loads(requests[0].split(b'\r\n\r\n',1)[1])
    assert not {'report_id','source_ids','executor_id','task_id','run_id'} & body.keys()
