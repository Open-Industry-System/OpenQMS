"""Restart-bound restricted text policy; no private terms in diagnostics or repr."""
import hashlib
import hmac
import json
import os
import stat
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from app.services.agent_runtime.trial_policy import _Entry, _unique_keys, MAX_FILE_BYTES
from app.services.capa_d4_redaction import RULE_VERSION, validate_terms

TEXT_WORKER_SHA256 = '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21'
TEXT_WORKER_PATH = Path(__file__).resolve().parents[3] / 'examples' / 'readonly_d4_text_receiver.py'
TEXT_PLUGIN_KEY = 'openqms.local-d4-root-cause-text'


class _TextEntry(_Entry):
    model_config = ConfigDict(extra='forbid', frozen=True)
    plugin_key: Literal['openqms.local-d4-root-cause-text']
    worker_sha256: Literal[TEXT_WORKER_SHA256]
    redaction_terms: list[str] = Field(default_factory=list, max_length=50)

    @field_validator('redaction_terms', mode='before')
    @classmethod
    def strict_terms(cls, value):
        return list(validate_terms(value))


@dataclass(frozen=True)
class TextEntry:
    tenant_id: object
    tenant_generation: int
    installation_id: object
    credential_epoch: int
    plugin_key: str
    plugin_version: str
    executor_user_id: object
    report_id: object
    factory_id: object
    product_line_code: str
    expires_at: object
    worker_sha256: str
    redaction_terms: tuple[str, ...] = field(repr=False)
    binding_sha256: str = field(repr=False)


@dataclass(frozen=True)
class TextPolicy:
    entries: tuple[TextEntry, ...]
    diagnostic: str


EMPTY_TEXT_POLICY = TextPolicy((), 'TEXT_POLICY_DISABLED')


def _read_policy(path):
    """Open every path component without following links, then read one descriptor."""
    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    directory = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in parts[1:-1]:
            next_directory = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('unsafe directory')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
                    or info.st_size > MAX_FILE_BYTES):
                raise ValueError('unsafe file')
            chunks, size = [], 0
            while chunk := os.read(fd, min(8192, MAX_FILE_BYTES + 1 - size)):
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ValueError('oversized file')
            return b''.join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def load_text_policy(path, *, enabled, runtime_enabled, tenant_mode, now, key):
    if not enabled or not runtime_enabled:
        return EMPTY_TEXT_POLICY
    if tenant_mode != 'dev':
        return TextPolicy((), 'TEXT_MODE_DENIED')
    if not path:
        return EMPTY_TEXT_POLICY
    try:
        if now.tzinfo is None or now.utcoffset() is None or not isinstance(key, bytes) or not key:
            raise ValueError('invalid settings')
        raw = _read_policy(path)
        payload = json.loads(raw, object_pairs_hook=_unique_keys, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (type(payload) is not dict or set(payload) != {'schema_version', 'entries'}
                or type(payload['schema_version']) is not int or payload['schema_version'] != 1
                or type(payload['entries']) is not list or len(payload['entries']) > 1):
            raise ValueError('invalid envelope')
        if hashlib.sha256(TEXT_WORKER_PATH.read_bytes()).hexdigest() != TEXT_WORKER_SHA256:
            raise ValueError('worker mismatch')
        entries = []
        for item in payload['entries']:
            row = _TextEntry.model_validate(item)
            if not now < row.expires_at <= now + timedelta(hours=1):
                raise ValueError('invalid validity')
            normalized = row.model_dump(mode='json')
            encoded = json.dumps({'entry': normalized, 'rule_version': RULE_VERSION},
                sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
            digest = hmac.new(key, b'openqms.d4.text-policy.v1\n' + encoded, hashlib.sha256).hexdigest()
            values = row.model_dump()
            values['redaction_terms'] = tuple(values['redaction_terms'])
            entries.append(TextEntry(**values, binding_sha256=digest))
        return TextPolicy(tuple(entries), 'TEXT_POLICY_READY')
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        return TextPolicy((), 'TEXT_POLICY_INVALID')
