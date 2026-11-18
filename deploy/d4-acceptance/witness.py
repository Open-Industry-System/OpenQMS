"""Read-only D4 business evidence from an explicitly owned synthetic cluster."""
from dataclasses import dataclass
import json
import re
import subprocess
import time
from uuid import UUID


DATABASE = 'qms_d4_acceptance'
ROLE = 'openqms_d4_witness'
CAPABILITY = 'capa.d4.root_cause_candidate.masked.v1'
PLUGIN = 'openqms.local-d4-root-cause-text'
LEASE_LABEL = 'openqms.d4-acceptance.lease'
ROLE_LABEL = 'openqms.d4-acceptance.role'
DOCKER = ('/usr/bin/docker', '--host', 'unix:///var/run/docker.sock')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def uuid_text(value):
    require(isinstance(value, str) and len(value) == 36, 'invalid witness UUID')
    require(str(UUID(value)) == value, 'noncanonical witness UUID')
    return value


def checked_output(*command, text=None, deadline=None):
    timeout = 15 if deadline is None else min(15, deadline - time.monotonic())
    if timeout <= 0:
        raise TimeoutError('trusted witness deadline expired')
    try:
        result = subprocess.run(command, input=text, text=True, capture_output=True,
                                timeout=timeout, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
    except subprocess.TimeoutExpired:
        raise TimeoutError('trusted witness deadline expired') from None
    require(result.returncode == 0 and len(result.stdout) < 131072,
            'trusted witness command failed')
    return json.loads(result.stdout)


@dataclass(frozen=True)
class Snapshot:
    report_id: str
    task_id: str
    installation_id: str
    grant_id: str
    run_id: str | None
    task_status: str
    run_status: str | None
    lease_epoch: int | None
    accepted_message_seq: int | None
    grant_enabled: bool
    grant_live: bool
    receipts: int
    committed_audits: int
    revoke_audits: int
    finish_audits: int
    run_live: bool


class PsqlWitness:
    def __init__(self, container_id, image_id, system_identifier, slot_lease,
                 tenant_id, schema, generation):
        require(re.fullmatch('[0-9a-f]{64}', container_id), 'exact database container ID required')
        require(re.fullmatch('sha256:[0-9a-f]{64}', image_id), 'exact database image ID required')
        require(re.fullmatch('[1-9][0-9]{0,19}', system_identifier), 'exact cluster identity required')
        require(re.fullmatch('[0-9a-f]{32}', slot_lease), 'invalid database ownership lease')
        require(re.fullmatch('tenant_[a-z0-9_]{1,56}', schema), 'dedicated tenant schema required')
        require(type(generation) is int and 0 <= generation <= 2147483647, 'invalid tenant generation')
        self.container_id = container_id
        self.image_id = image_id
        self.system_identifier = system_identifier
        self.slot_lease = slot_lease
        self.tenant_id = uuid_text(tenant_id)
        self.schema = schema
        self.generation = generation

    def verify_owned_database(self, deadline=None):
        [live] = checked_output(*DOCKER, 'container', 'inspect', self.container_id, deadline=deadline)
        labels = live['Config']['Labels']
        networks = live['NetworkSettings']['Networks']
        expected_network = 'openqms-d4-' + self.slot_lease
        require(live['Id'] == self.container_id and live['Image'] == self.image_id
                and live['State']['Running'] is True
                and labels.get(LEASE_LABEL) == self.slot_lease
                and labels.get(ROLE_LABEL) == 'postgres'
                and set(networks) == {expected_network}
                and not live['HostConfig'].get('PortBindings')
                and not any((live['NetworkSettings'].get('Ports') or {}).values()),
                'database is not the isolated synthetic deployment')
        network_id = networks[expected_network]['NetworkID']
        require(re.fullmatch('[0-9a-f]{64}', network_id), 'invalid database network identity')
        [network] = checked_output(*DOCKER, 'network', 'inspect', network_id, deadline=deadline)
        require(network['Id'] == network_id and network['Name'] == expected_network
                and network['Internal'] is True and network['Driver'] == 'bridge'
                and network['Labels'].get(LEASE_LABEL) == self.slot_lease,
                'database network ownership mismatch')

    def snapshot(self, report_id, task_id, installation_id, grant_id, run_id=None, *, deadline=None):
        report_id, task_id, installation_id, grant_id = map(
            uuid_text, (report_id, task_id, installation_id, grant_id)
        )
        if run_id is not None:
            uuid_text(run_id)
        self.verify_owned_database(deadline)
        sql = self.snapshot_sql(report_id, task_id, installation_id, grant_id)
        result = checked_output(
            *DOCKER, 'container', 'exec', '--interactive', '--user', '65534:65534', self.container_id,
            '/usr/bin/env', '-i', 'PATH=/usr/bin:/bin', '/usr/bin/psql', '--no-psqlrc', '--no-password',
            '--quiet', '--tuples-only', '--no-align', '--set', 'ON_ERROR_STOP=1', '--dbname', DATABASE,
            '--username', ROLE, '--host', '/var/run/postgresql', '--file', '-', text=sql,
            deadline=deadline,
        )
        require(isinstance(result, dict), 'exact tenant, report, task, installation and grant not witnessed')
        data = Snapshot(**result)
        require(data.report_id == report_id and data.task_id == task_id
                and data.installation_id == installation_id and data.grant_id == grant_id
                and (run_id is None or run_id == data.run_id),
                'snapshot identity mismatch')
        require(all(type(value) is bool for value in (data.grant_enabled, data.grant_live, data.run_live))
                and all(type(value) is int and value >= 0 for value in (
                    data.receipts, data.committed_audits, data.revoke_audits, data.finish_audits)),
                'invalid witness metadata')
        return data

    def snapshot_sql(self, report, task, installation, grant):
        # Only canonical UUID, digit and identifier values are interpolated.
        report, task, installation, grant = map(uuid_text, (report, task, installation, grant))
        ns = '"' + self.schema + '"'
        return f"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL search_path = pg_catalog;
SELECT current_database() = '{DATABASE}' AND current_user = '{ROLE}'
   AND (pg_control_system()).system_identifier::text = '{self.system_identifier}'
   AND EXISTS (
       SELECT 1 FROM pg_roles WHERE rolname = current_user AND NOT
       (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)
   )
   AND NOT pg_has_role('pg_write_all_data', 'MEMBER') AS witness_isolated
\\gset
\\if :witness_isolated
WITH scoped_task AS (
    SELECT t.task_id, t.status, t.executor_user_id
    FROM {ns}.agent_tasks t
    JOIN {ns}.agent_plugin_installations i ON i.installation_id = t.preferred_installation_id
    WHERE t.task_id = '{task}'::uuid AND t.target_capa_id = '{report}'::uuid
      AND i.installation_id = '{installation}'::uuid AND i.plugin_key = '{PLUGIN}'
), scoped_grant AS (
    SELECT g.enabled, g.expires_at
    FROM {ns}.agent_plugin_grants g
    JOIN {ns}.agent_plugin_derived_source_scopes s ON s.plugin_grant_id = g.grant_id
    WHERE g.grant_id = '{grant}'::uuid AND g.installation_id = '{installation}'::uuid
      AND g.capability_id = '{CAPABILITY}' AND s.target_report_id = '{report}'::uuid
      AND EXISTS (
          SELECT 1 FROM {ns}.agent_task_grants tg
          JOIN {ns}.agent_d4_task_parent_grants parent ON parent.task_grant_id = tg.grant_id
          WHERE tg.task_id = '{task}'::uuid AND tg.capability_id = '{CAPABILITY}'
            AND parent.plugin_grant_id = g.grant_id
      )
), task_runs AS (
    SELECT run_id, installation_id, status, lease_epoch, accepted_message_seq, lease_expires_at
    FROM {ns}.agent_runs WHERE task_id = '{task}'::uuid
), receipts AS (
    SELECT receipt_id, run_id, source_capa_id, tenant_generation, projection_id,
           projection_digest, data_class, lease_epoch
    FROM {ns}.agent_restricted_projection_receipts
    WHERE task_id = '{task}'::uuid
), committed AS (
    SELECT a.record_id
    FROM {ns}.audit_logs a
    JOIN receipts p ON p.receipt_id = a.record_id AND p.run_id = a.correlation_id
    JOIN scoped_task t ON t.executor_user_id = a.operated_by
    WHERE a.table_name = 'agent_restricted_projection_receipts'
      AND a.action = 'D4_TEXT_RELEASE_COMMITTED'
      AND a.changed_fields->>'task_id' = '{task}'
      AND a.changed_fields->>'run_id' = p.run_id::text
      AND a.changed_fields->>'receipt_id' = p.receipt_id::text
      AND a.changed_fields->>'projection_id' = '{CAPABILITY}'
      AND a.changed_fields->>'projection_digest' = p.projection_digest
      AND a.changed_fields->>'outcome' = 'release_committed'
)
SELECT json_build_object(
    'report_id','{report}', 'task_id',t.task_id, 'installation_id','{installation}', 'grant_id','{grant}',
    'task_status',t.status, 'run_id',r.run_id, 'run_status',r.status, 'lease_epoch',r.lease_epoch,
    'accepted_message_seq',r.accepted_message_seq, 'grant_enabled',g.enabled,
    'grant_live',g.enabled AND coalesce(g.expires_at > now(),false),
    'run_live',coalesce(r.status = 'active' AND r.lease_expires_at > now(),false),
    'receipts',(SELECT count(*) FROM receipts),
    'committed_audits',(SELECT count(*) FROM committed),
    'finish_audits',(
        SELECT count(*) FROM {ns}.audit_logs a
        WHERE a.record_id = r.run_id AND a.table_name = 'agent_runs'
          AND a.action = 'FINISH_AGENT_RUN' AND a.operated_by = t.executor_user_id
          AND a.changed_fields->>'task_id' = '{task}' AND a.changed_fields->>'run_id' = r.run_id::text
          AND a.changed_fields->>'status' = 'completed'
          AND a.changed_fields->>'lease_epoch' = r.lease_epoch::text
    ),
    'revoke_audits',(
        SELECT count(*) FROM {ns}.audit_logs a
        WHERE a.record_id = '{grant}'::uuid AND a.table_name = 'agent_plugin_grants'
          AND a.action = 'SET_PLUGIN_GRANT_ENABLED'
          AND a.changed_fields->>'grant_id' = '{grant}'
          AND a.changed_fields->>'installation_id' = '{installation}'
          AND a.changed_fields->>'capability_id' = '{CAPABILITY}'
          AND a.changed_fields->'enabled' = 'false'::jsonb
    )
)
FROM scoped_task t CROSS JOIN scoped_grant g LEFT JOIN task_runs r ON true
WHERE EXISTS (
      SELECT 1 FROM public.tenants
      WHERE id = '{self.tenant_id}'::uuid AND schema_name = '{self.schema}'
        AND generation = {self.generation} AND status = 'active'
  )
  AND (SELECT count(*) FROM task_runs) <= 1
  AND (r.run_id IS NULL OR r.installation_id = '{installation}'::uuid)
  AND NOT EXISTS (
      SELECT 1 FROM receipts p
      WHERE p.run_id IS DISTINCT FROM r.run_id OR p.source_capa_id <> '{report}'::uuid
         OR p.tenant_generation <> {self.generation} OR p.projection_id <> '{CAPABILITY}'
         OR p.data_class <> 'restricted'
         OR p.lease_epoch <> r.lease_epoch - CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END
  );
\\else
\\echo null
\\endif
ROLLBACK;
"""


def same_subject(before, after):
    require(
        (before.report_id, before.task_id, before.installation_id, before.grant_id)
        == (after.report_id, after.task_id, after.installation_id, after.grant_id),
        'scenario changed subjects',
    )


def verify_delivery(before, after):
    same_subject(before, after)
    require(before.task_status == 'ready' and before.run_status == 'pending' and before.grant_live
            and before.lease_epoch == before.accepted_message_seq == 0
            and before.receipts == before.committed_audits == before.finish_audits == 0
            and before.run_id is not None and before.run_id == after.run_id
            and after.task_status == after.run_status == 'completed' and after.lease_epoch == 2
            and after.accepted_message_seq == 1 and after.grant_live
            and after.receipts == after.committed_audits == after.finish_audits == 1
            and after.revoke_audits == before.revoke_audits,
            'no unique completed D4 delivery and matching audit were witnessed')


def verify_revocation(before, after, observation):
    same_subject(before, after)
    expected_observation = dict(
        task_id=before.task_id, run_id=before.run_id, report_id=before.report_id,
        installation_id=before.installation_id, grant_id=before.grant_id,
        authorized_status=200, revoked_status=401, revoked_body_received=False,
    )
    require(isinstance(observation, dict) and set(observation) == set(expected_observation)
            and all(type(observation[k]) is type(v) and observation[k] == v
                    for k, v in expected_observation.items()),
            'trusted wire observation of same-run revocation required')
    require(before.run_id is not None and before.run_id == after.run_id
            and before.run_status == after.run_status == 'active'
            and before.run_live and after.run_live and before.task_status == after.task_status == 'ready'
            and before.lease_epoch == after.lease_epoch == 1 and before.grant_live
            and before.finish_audits == after.finish_audits == 0
            and not after.grant_enabled and before.receipts == before.committed_audits == 1
            and after.receipts == before.receipts and after.committed_audits == before.committed_audits
            and after.revoke_audits == before.revoke_audits + 1,
            'same-run revoke or absence of new D4 delivery was not witnessed')
