"""HTTP-authorized local metadata trial CLI; no database or maintenance credentials."""
import argparse
from datetime import UTC, datetime
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from app.schemas.agent_plugin import LocalTrialRevoke, LocalTrialRevokeOut
from app.services.agent_runtime.trial_launcher import MAX_OUTPUT, local_origin, run_fixed_worker
from app.services.agent_runtime.trial_policy import load_policy, read_private_file, _unique_keys


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def revoke_http(*, installation_id: UUID, expected_epoch: int, tenant_slug: str,
                api_base_url: str, admin_token_file: Path) -> LocalTrialRevokeOut:
    origin = local_origin(api_base_url)
    request_body = LocalTrialRevoke(expected_credential_epoch=expected_epoch)
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', tenant_slug):
        raise ValueError('invalid tenant')
    token = read_private_file(admin_token_file, limit=16384).decode('utf-8').strip()
    if not token or re.fullmatch(r'[A-Za-z0-9._-]+', token) is None:
        raise ValueError('invalid token file')
    request = Request(origin+f'/api/admin/agent-plugins/{installation_id}/revoke-local-trial',
        data=json.dumps(request_body.model_dump()).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
            'Authorization': 'Bearer '+token, 'X-Tenant-ID': tenant_slug})
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError('invalid revoke status')
        raw = response.read(MAX_OUTPUT+1)
        if len(raw) > MAX_OUTPUT:
            raise ValueError('oversized revoke response')
    payload = json.loads(raw, object_pairs_hook=_unique_keys)
    if (not isinstance(payload, dict) or payload.get('installation_id') != str(installation_id)
            or type(payload.get('credential_epoch')) is not int
            or not 0 <= payload['credential_epoch'] <= 2147483647
            or payload.get('enabled') is not False):
        raise ValueError('invalid revoke types')
    result = LocalTrialRevokeOut.model_validate(payload)
    if (result.installation_id != installation_id
            or (result.outcome == 'revoked' and result.credential_epoch != expected_epoch+1)
            or (result.outcome == 'already_fenced' and result.credential_epoch <= expected_epoch)):
        raise ValueError('invalid revoke proof')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Trusted-host D4 metadata trial only')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check-policy')
    check.add_argument('--policy-file', required=True, type=Path)
    run = commands.add_parser('run')
    revoke = commands.add_parser('revoke')
    for command in (run, revoke):
        command.add_argument('--installation-id', required=True, type=UUID)
        command.add_argument('--tenant-slug', required=True)
        command.add_argument('--api-base-url', required=True)
    run.add_argument('--installation-secret-file', required=True, type=Path)
    run.add_argument('--claim-key', default='readonly-8d-v1')
    run.add_argument('--checkpoint', choices=('off', 'save'), default='off')
    run.add_argument('--finish', choices=('off', 'completed'), default='off')
    revoke.add_argument('--expected-credential-epoch', required=True, type=int)
    revoke.add_argument('--admin-token-file', required=True, type=Path)
    arguments = parser.parse_args(argv)
    if arguments.command == 'check-policy':
        policy = load_policy(arguments.policy_file, mode='local_metadata', tenant_mode='dev', now=datetime.now(UTC))
        print(json.dumps({'diagnostic': policy.diagnostic, 'entries': len(policy.entries),
            'file_sha256': policy.file_sha256}))
        return 0 if policy.diagnostic == 'TRIAL_READY' else 1
    if arguments.command == 'run':
        return run_fixed_worker(installation_id=arguments.installation_id,
            secret_file=arguments.installation_secret_file, tenant_slug=arguments.tenant_slug,
            api_base_url=arguments.api_base_url, claim_key=arguments.claim_key,
            checkpoint=arguments.checkpoint, finish=arguments.finish)
    try:
        result = revoke_http(installation_id=arguments.installation_id,
            expected_epoch=arguments.expected_credential_epoch, tenant_slug=arguments.tenant_slug,
            api_base_url=arguments.api_base_url, admin_token_file=arguments.admin_token_file)
        print(result.model_dump_json())
        return 0
    except (OSError, ValueError, TypeError, RecursionError, URLError, HTTPException):
        print('TRIAL_REVOKE_DENIED', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
