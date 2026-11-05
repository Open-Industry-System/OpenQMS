"""Closed fixture protocol, not a worker launcher or production entry point.

Only SDK + stdlib are imported. Inputs and message contents are never executed;
stdout is an allowlist of IDs, counts, states, error types and boolean flags.
"""
import json
import os
from pathlib import Path
import sys
from uuid import UUID

import openqms_agent_sdk
from openqms_agent_sdk import (
    ClientConfig, EventPayload, InstallationClient, ResultPayload, SDKError,
)


class Probe:
    def __init__(self, config):
        assert sys.flags.isolated and sys.prefix != sys.base_prefix
        assert Path(openqms_agent_sdk.__file__).is_relative_to(Path(sys.prefix))
        assert set(os.environ) <= {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}
        assert not any(name.split('.')[0] in {'app', 'httpx', 'sqlalchemy'} for name in sys.modules)
        self.config = config
        self.client = InstallationClient(ClientConfig(config['origin'], tenant_slug=config['tenant'],
            timeout=5, response_budget=64 * 1024), UUID(config['installation_id']), config['secret'])
        self.run = self.previous = self.batch = None
        self.receipts = {}

    def command(self, command):
        action = command['action']
        run = self.previous if command.get('previous', False) else self.run
        if action == 'tenant_claim':
            foreign = InstallationClient(ClientConfig(self.config['origin'], tenant_slug=command['tenant'], timeout=5),
                UUID(self.config['installation_id']), self.config['secret'])
            try:
                foreign.claim_run(request_key='foreign-tenant-claim')
                return {'unexpected_success': True}
            finally:
                foreign.close()
        if action == 'claim':
            self.previous = self.run
            self.run = self.client.claim_run(request_key=command.get('key', 'sdk-process-claim'))
            return {'run_id': str(self.run.claim.run_id), 'task_id': str(self.run.claim.task_id),
                'accepted': self.run.claim.accepted_message_seq, 'isolated': True}
        if action == 'capabilities':
            result = run.capabilities()
            return {'count': len(result.capabilities), 'summary_allowed': any(
                item.id == 'capa.d4.summary.masked.v1' and item.allowed for item in result.capabilities)}
        if action == 'messages':
            self.batch = run.claim_messages()
            return {'count': len(self.batch.messages), 'accepted': self.batch.accepted_sequence,
                'sequences': [message.sequence for message in self.batch.messages]}
        if action == 'ack':
            result = run.ack_messages(batch_id=self.batch.batch_id, through_sequence=command['through'])
            return {'accepted': result.accepted_sequence}
        if action == 'context':
            view = command.get('view', 'report')
            report_id = UUID(command['report_id']) if 'report_id' in command else None
            result = run.get_capa_context(report_id=report_id, view=view)
            self.receipts[view] = result
            self.receipts.setdefault('old', result)
            return {'receipt_id': str(result.receipt_id), 'report_id': str(result.report_id),
                'verifications_none': result.verifications is None,
                'count': 0 if result.verifications is None else len(result.verifications),
                'tuple': result.verifications is None or isinstance(result.verifications, tuple)}
        if action in ('event', 'result', 'checkpoint'):
            view = 'verifications' if command.get('alternate_source') else 'report'
            context = self.receipts['old' if command.get('old_receipt') else view]
            receipts = (context.receipt_id,)
            key = command.get('key', 'sdk-'+action)
            if action == 'event':
                result = run.record_event(idempotency_key=key, event_type='query_completed',
                    payload=EventPayload(completed=2 if command.get('changed') else 1, total=2), receipt_ids=receipts)
                identifier = result.event_id
            elif action == 'result':
                result = run.save_result(idempotency_key=key, payload=ResultPayload(
                    explanations=('changed' if command.get('changed') else 'metadata only',)), receipt_ids=receipts)
                identifier = result.result_id
            else:
                result = run.save_checkpoint(idempotency_key=key, receipt_ids=receipts)
                identifier = result.checkpoint_id
            fields = ('receipt_id', 'source_capa_id', 'projection_id', 'projection_digest', 'data_class')
            matches = len(result.sources) == 1 and all(
                getattr(result.sources[0], field) == getattr(context, field) for field in fields)
            return {'id': str(identifier), 'sources': len(result.sources), 'source_matches': matches}
        if action == 'history':
            result = run.message_history(after_sequence=command.get('after', 0))
            return {'count': len(result.messages), 'next': result.next_sequence, 'complete': result.complete,
                'sequences': [message.sequence for message in result.messages]}
        if action == 'finish':
            result = run.finish(status='completed')
            return {'task_status': result.task_status, 'run_status': result.run_status, 'state': run.state}
        return {'fatal': 'UnsupportedAction'}


def main():
    probe = None
    try:
        probe = Probe(json.loads(sys.stdin.readline()))
        for line in sys.stdin:
            try:
                result = probe.command(json.loads(line))
            except SDKError as error:
                result = {'error': type(error).__name__, 'status': error.status,
                    'sent': error.may_have_been_sent, 'unknown': error.outcome_unknown,
                    'state': None if probe.run is None else probe.run.state}
            except Exception as error:
                result = {'fatal': type(error).__name__}
            print(json.dumps(result), flush=True)
    except Exception as error:
        print(json.dumps({'fatal': type(error).__name__}), flush=True)
    finally:
        if probe is not None:
            probe.client.close()


if __name__ == '__main__':
    main()
