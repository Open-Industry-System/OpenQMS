"""Deployment-owned, immutable local metadata policy. Invalid input fails closed."""
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

WORKER_SHA256 = 'ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54'
WORKER_PATH = Path(__file__).resolve().parents[3] / 'examples' / 'readonly_8d_plugin.py'
MAX_FILE_BYTES = 128 * 1024


@dataclass(frozen=True)
class TrialEntry:
    tenant_id: UUID
    tenant_generation: int
    installation_id: UUID
    credential_epoch: int
    plugin_key: str
    plugin_version: str
    executor_user_id: UUID
    report_id: UUID
    factory_id: UUID
    product_line_code: str
    expires_at: datetime
    worker_sha256: str
    binding_sha256: str


@dataclass(frozen=True)
class TrialPolicy:
    entries: tuple[TrialEntry, ...]
    diagnostic: str
    file_sha256: str | None = None


EMPTY_POLICY = TrialPolicy((), 'TRIAL_DISABLED')


class _Entry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    tenant_id: UUID
    tenant_generation: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    installation_id: UUID
    credential_epoch: Annotated[StrictInt, Field(ge=0, le=2147483646)]
    plugin_key: Literal['openqms.local-d4-metadata']
    plugin_version: Literal['1.0.0']
    executor_user_id: UUID
    report_id: UUID
    factory_id: UUID
    product_line_code: Annotated[StrictStr, Field(min_length=1, max_length=50)]
    expires_at: datetime
    worker_sha256: Literal[WORKER_SHA256]

    @field_validator('tenant_id', 'installation_id', 'executor_user_id', 'report_id', 'factory_id', mode='before')
    @classmethod
    def canonical_uuid(cls, value):
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError('noncanonical UUID')
        return value

    @field_validator('product_line_code')
    @classmethod
    def exact_product_line(cls, value):
        if '*' in value or '?' in value:
            raise ValueError('wildcard scope')
        return value

    @field_validator('expires_at', mode='before')
    @classmethod
    def aware_time(cls, value):
        if not isinstance(value, str):
            raise ValueError('timestamp required')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed.astimezone(UTC)


class _Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: StrictInt
    entries: list[_Entry] = Field(max_length=20)

    @field_validator('schema_version')
    @classmethod
    def version_one(cls, value):
        if value != 1:
            raise ValueError('unsupported version')
        return value


def read_private_file(path: Path, *, limit: int) -> bytes:
    """Read one descriptor; never block on FIFO or follow a substituted symlink."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) not in (0o400, 0o600)
                or metadata.st_size > limit):
            raise ValueError('unsafe file')
        chunks, size = [], 0
        while chunk := os.read(fd, min(8192, limit + 1 - size)):
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise ValueError('oversized file')
        return b''.join(chunks)
    finally:
        os.close(fd)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def load_policy(path: Path | str | None, *, mode: str, tenant_mode: str, now: datetime) -> TrialPolicy:
    if mode == 'disabled':
        return EMPTY_POLICY
    if mode != 'local_metadata':
        return TrialPolicy((), 'TRIAL_POLICY_INVALID')
    if tenant_mode != 'dev':
        return TrialPolicy((), 'TRIAL_MODE_DENIED')
    if path is None or path == '':
        return EMPTY_POLICY
    try:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('aware clock required')
        raw = read_private_file(Path(path), limit=MAX_FILE_BYTES)
        payload = json.loads(raw, object_pairs_hook=_unique_keys)
        envelope = _Envelope.model_validate(payload)
        if hashlib.sha256(WORKER_PATH.read_bytes()).hexdigest() != WORKER_SHA256:
            raise ValueError('worker mismatch')
        entries, keys, installs = [], set(), {}
        for row in envelope.entries:
            if not now < row.expires_at <= now + timedelta(hours=24):
                raise ValueError('invalid validity window')
            key = (row.tenant_id, row.tenant_generation, row.installation_id, row.executor_user_id, row.report_id)
            install_key = (row.tenant_id, row.installation_id)
            identity = (row.plugin_key, row.plugin_version, row.credential_epoch, row.worker_sha256)
            if key in keys or (install_key in installs and installs[install_key] != identity):
                raise ValueError('inconsistent declarations')
            keys.add(key)
            installs[install_key] = identity
            normalized = row.model_dump(mode='json')
            encoded = json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            entries.append(TrialEntry(**row.model_dump(), binding_sha256=hashlib.sha256(encoded).hexdigest()))
        return TrialPolicy(tuple(entries), 'TRIAL_READY', hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        return TrialPolicy((), 'TRIAL_POLICY_INVALID')


@dataclass(frozen=True)
class TrialAdmission:
    profile: str
    binding_sha256: str
    expires_at: datetime
    installation_id: UUID


def select_admission(policy: TrialPolicy, *, binding, installation, executor_user_id: UUID,
                     report_id: UUID, factory_id: UUID, product_line_code: str,
                     now: datetime) -> TrialAdmission | None:
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    if (settings.TENANT_MODE != 'dev' or not isinstance(policy, TrialPolicy)
            or not isinstance(binding, TenantBinding) or binding.mode != 'business'
            or now.tzinfo is None or policy.diagnostic != 'TRIAL_READY'):
        return None
    for row in policy.entries:
        if (row.tenant_id == binding.tenant_id and row.tenant_generation == binding.generation
                and row.installation_id == installation.installation_id
                and row.credential_epoch == installation.credential_epoch
                and row.plugin_key == installation.plugin_key and row.plugin_version == installation.plugin_version
                and row.executor_user_id == executor_user_id and row.report_id == report_id
                and row.factory_id == factory_id and row.product_line_code == product_line_code
                and now < row.expires_at):
            return TrialAdmission('local_metadata_v1', row.binding_sha256, row.expires_at, row.installation_id)
    return None
