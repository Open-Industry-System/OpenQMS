"""Fixture-only communication, NOT an admitted worker or production launcher.

Read one explicit JSON object from stdin; never credentials in argv/environment,
.env, profiles, or official fixed-worker CLI/hash. Default: claim + capabilities.
Optional operations: get_capa_context (report/verifications view) and message_history.
No message claim/ACK: this CLI cannot hand message bodies to a caller safely.
No event/result/checkpoint/finish automation, retries, model or business writes.
The normal server policy must authorize every operation; this grants no profile.
"""
import json
import sys

from openqms_agent_sdk import ClientConfig, InstallationClient, SDKError


def validate_options(config):
    if not isinstance(config, dict):
        raise ValueError('invalid_input')
    operations = config.get('operations', [])
    if not isinstance(operations, list) or len(operations) > 10:
        raise ValueError('invalid_operations')
    for item in operations:
        if not isinstance(item, dict) or set(item) - {'operation', 'params'}:
            raise ValueError('invalid_operation')
        operation, params = item.get('operation'), item.get('params', {})
        if not isinstance(params, dict):
            raise ValueError('invalid_parameters')
        if operation == 'get_capa_context':
            if set(params) - {'report_id', 'view'} or params.get('view', 'report') not in ('report', 'verifications'):
                raise ValueError('invalid_context')
        elif operation == 'message_history':
            if set(params) - {'after_sequence', 'limit'}:
                raise ValueError('invalid_history')
        else:
            raise ValueError('unsupported_operation')
    return operations


def session(config, *, client_type=InstallationClient):
    operations = validate_options(config)
    client = client_type(ClientConfig(config['origin'], config['tenant']),
                         config['installation_id'], config['secret'])
    run = None
    try:
        run = client.claim_run(request_key=config['request_key'])
        caps = run.capabilities()
        output = {'status': 'ok', 'capabilities': len(caps.capabilities)}
        summaries = []
        for item in operations:
            operation, params = item['operation'], item.get('params', {})
            if operation == 'get_capa_context':
                context = run.get_capa_context(**params)
                summaries.append({'operation': operation, 'receipt_id': str(context.receipt_id)})
            else:
                history = run.message_history(**params)
                summaries.append({'operation': operation, 'messages': len(history.messages),
                                  'complete': history.complete})
        if summaries:
            output['operations'] = summaries
        return output
    finally:
        if run is not None:
            run.close()  # local credential-reference drop, not remote finish
        client.close()


def main():
    if len(sys.argv) != 1:
        print('{"status":"invalid_input"}')
        return 2
    try:
        # Bound input; never echo malformed input, exception text or SDK DTO repr.
        text = sys.stdin.read(1024 * 1024 + 1)
        if len(text) > 1024 * 1024:
            raise ValueError('input_too_large')
        result = session(json.loads(text))
    except SDKError:
        print('{"status":"sdk_error"}')
        return 1
    except Exception:
        print('{"status":"invalid_input"}')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
