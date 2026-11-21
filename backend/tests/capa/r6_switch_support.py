"""Actual owned CLI fixtures. No phase UPDATE or fake settle callback."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from sqlalchemy import text

from app.services.capa_switch_evidence import digest

ROOT=Path(__file__).resolve().parents[3]



async def owned_cli(case,tmp_path, *, runtime_pid=None, deployment_config=None, expiry_minutes=15):
    # This integration lane is intentionally explicit: an unknown environment
    # is refused, never treated as an exercise just because its DB ends _test.
    resource_path=os.environ['OPENQMS_TEST_RESOURCE_FILE']
    resource=json.loads(Path(resource_path).read_text())
    from datetime import datetime,timedelta,timezone
    from app.services.capa_switch_evidence import runtime_manifest
    environment_id='owned-r6-'+resource['owner_nonce']
    namespace=dict(tenant_id=str(case.binding.tenant_id),schema=case.binding.schema_name,generation=case.binding.generation)
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'deployment_role':'synthetic_exercise','owner':resource['owner_nonce'],
        'environment_id':environment_id,'tenant':namespace, **({'execution':deployment_config} if deployment_config else {})}))
    async with case.session() as db:
        actual=(await db.execute(text('SELECT current_database(),current_user,(pg_control_system()).system_identifier::text'))).one()
        public=await db.scalar(text('SELECT version_num FROM public.alembic_version'))
        tenant=await db.scalar(text('SELECT version_num FROM tenant_schema_version'))
    sources=runtime_manifest(ROOT)
    executable=str(Path(sys.executable).resolve())
    executable_digest=hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    config_digest=hashlib.sha256(config.read_bytes()).hexdigest()
    build_artifact=dict(source_manifest=sources,source_root=str(ROOT),executable=executable,
        executable_digest=executable_digest,config_digest=config_digest,roles=['server','worker'],schema_heads=[public,tenant],
        source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    build=digest(build_artifact)
    def artifact(name,value):
        path=tmp_path/name
        path.write_text(json.dumps(value,sort_keys=True))
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    builds={build:artifact('build.json',build_artifact)}
    target=dict(environment='isolated_exercise',deployment_role='synthetic_exercise',environment_id=environment_id,
        owner=resource['owner_nonce'],database=actual[0],database_role=actual[1],system_identifier=actual[2],
        tenant=namespace,public_head=public,tenant_head=tenant,candidate_build=build,compatible_build=build,
        source_manifest=digest(sources),config_digest=config_digest)
    launch_pid=runtime_pid or os.getpid()
    observed=subprocess.check_output(['ps','-p',str(launch_pid),'-o','lstart=','-o','command='],text=True).strip()
    launch_key=uuid4().hex+uuid4().hex
    launch=dict(pid=launch_pid,start=observed[:24],command_digest=hashlib.sha256(observed.encode()).hexdigest(),
        build=build,role='server',deployment_role='synthetic_exercise',owner=target['owner'],executable=executable,
        executable_digest=executable_digest,config_digest=config_digest)
    launch['signature']=hmac.new(launch_key.encode(),digest(launch).encode(),hashlib.sha256).hexdigest()
    lease=artifact('exclusive-lease.json',dict(owner=target['owner'],environment_id=environment_id,tenant=namespace,deployment_role='synthetic_exercise'))
    record={'target':target,'resource_record':resource_path,'config_file':str(config),'instances':[artifact('launch.json',launch)],
        'operators':[str(case.actor().user_id)],'authorized_documents':[],'stopped_legacy_receipts':[],'build_artifacts':builds,'exclusive_lease':lease}
    key=uuid4().hex+uuid4().hex
    registry=tmp_path/'authority.json'
    def sign():
        registry.write_text(json.dumps({'record':record,'signature':hmac.new(key.encode(),digest(record).encode(),hashlib.sha256).hexdigest()}))
    sign()
    document=tmp_path/'exercise.json'
    document.write_text(json.dumps(dict(version=1,kind='exercise_input',purpose='r6-rehearsal.v1',
        exercise_id=str(uuid4()),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=expiry_minutes)).isoformat(),target=target,initial_epoch=0)))
    from app.services.capa_switch_evidence import Document
    def authorize_document(value):
        canonical=Document.model_validate(value).model_dump(mode='json',by_alias=True)
        sha=digest(canonical)
        record['authorized_documents'].append(sha)
        sign()
        return sha
    authorize_document(json.loads(document.read_text()))
    env=dict(os.environ,R6_SWITCH_AUTHORITY_FILE=str(registry),R6_SWITCH_AUTHORITY_KEY=key,R6_SWITCH_LAUNCH_ATTESTATION_KEY=launch_key,TENANT_MODE='dev')
    operation=str(uuid4())
    base=[sys.executable,'-B',str(ROOT/'backend/scripts/r6-entry-switch.py')]
    args=['--tenant',str(case.binding.tenant_id),'--actor',str(case.actor().user_id),'--operation',operation,'--document',str(document)]
    return dict(base=base,args=args,env=env,record=record,sign=sign,authorize_document=authorize_document,document=document,operation=operation,target=target,registry=registry)


async def cli(fixture,command,*extra):
    import asyncio
    process=await asyncio.create_subprocess_exec(*fixture['base'],command,*fixture['args'],*extra,
        env=fixture['env'],cwd=ROOT/'backend',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    out,err=await process.communicate()
    return process.returncode,json.loads(out or err)


from contextlib import asynccontextmanager


@asynccontextmanager
async def held_manual_writer(case, *, outcome='commit', value='admitted before durable close'):
    """Pause the real manual service exactly at its original transaction commit."""
    import asyncio
    from app.models.capa import CAPAEightD
    from app.services.capa_service import update_capa
    at_commit,release=asyncio.Event(),asyncio.Event()
    class IntentionalRollback(Exception):pass
    async with case.session() as writer:
        original_commit=writer.commit
        async def held_commit():
            at_commit.set()
            await release.wait()
            if outcome=='commit':await original_commit()
            else:
                await writer.rollback()
                raise IntentionalRollback()
        writer.commit=held_commit
        report=await writer.get(CAPAEightD,case.report_id)
        task=asyncio.create_task(update_capa(writer,report,{'d4_root_cause':value},case.actor().user_id))
        await asyncio.wait_for(at_commit.wait(),10)
        try:
            yield writer
        finally:
            release.set()
            try:await task
            except IntentionalRollback:
                assert outcome=='rollback'
