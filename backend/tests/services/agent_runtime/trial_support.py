import json
from pathlib import Path

WORKER_SHA256 = 'ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54'
UNIT_ENTRY = {
    'tenant_id': '00000000-0000-0000-0000-000000000001', 'tenant_generation': 1,
    'installation_id': '00000000-0000-0000-0000-000000000002', 'credential_epoch': 0,
    'plugin_key': 'openqms.local-d4-metadata', 'plugin_version': '1.0.0',
    'executor_user_id': '00000000-0000-0000-0000-000000000003',
    'report_id': '00000000-0000-0000-0000-000000000004',
    'factory_id': '00000000-0000-0000-0000-000000000005',
    'product_line_code': 'TRIAL-LINE', 'expires_at': '2030-01-01T00:20:00Z',
    'worker_sha256': WORKER_SHA256,
}


def write_policy(path: Path, entry: dict = UNIT_ENTRY) -> Path:
    with path.open('x', encoding='utf-8') as stream:
        path.chmod(0o600)
        json.dump({'schema_version': 1, 'entries': [entry]}, stream)
    return path
