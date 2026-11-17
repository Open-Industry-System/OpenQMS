"""Immutable I1 inputs; no Docker, network, subprocess or backend imports.

Deployment digests describe administrator-approved content, not attestation.
Secrets are hidden from repr/diagnostics, not securely erased from memory.
"""
from dataclasses import dataclass, field, fields
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from uuid import UUID

CONFIG_LIMIT = 64 * 1024
WORKER_SHA256 = '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21'
RECEIVER_ENTRYPOINT = ('python', '-I', '-S', '-B', '/receiver.py')
INFRASTRUCTURE_STATUSES = frozenset(('isolation_exited', 'isolation_terminated', 'isolation_unknown'))
# The kernel UID space is 32-bit and `-1`/`2**32-1` mean "no change". I1 only
# compares these values; reconciling them with the real kernel mapping is I4.
UID_MAX = 2**32 - 2


class ContractError(ValueError):
    def __init__(self):
        super().__init__('configuration_invalid')


def require(condition):
    if not condition:
        raise ContractError()


def _origin_port(origin):
    require(type(origin) is str)
    require(not any(ord(c) <= 32 or ord(c) >= 127 for c in origin))
    require(not any(c in origin for c in ('?', '#', '\\')))
    # urlsplit/port can raise with the supplied value. Discard that exception.
    parsed = port = None
    try:
        candidate = urlsplit(origin)
        raw_port = candidate.port
        parsed, port = candidate, raw_port
    except ValueError:
        parsed = port = None
    require(parsed is not None)
    require(parsed.scheme in ('http', 'https'))
    require(parsed.hostname in ('127.0.0.1', '::1'))
    require(parsed.username is None and parsed.password is None and parsed.path == '')
    port = port if port is not None else (443 if parsed.scheme == 'https' else 80)
    require(1 <= port <= 65535)
    authority = '[::1]' if parsed.hostname == '::1' else '127.0.0.1'
    require(parsed.netloc in (authority, authority + ':' + str(port)))
    return parsed.hostname, port


def _canonical_uuid(value):
    result = False
    try:
        result = str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        pass
    return result


@dataclass(frozen=True, slots=True, repr=False)
class PrivateConfig:
    origin: str
    tenant_slug: str
    installation_id: str
    secret: str = field(repr=False)
    request_key: str
    expected_report_id: str

    def __post_init__(self):
        require(all(type(getattr(self, item.name)) is str for item in fields(self)))
        _origin_port(self.origin)
        require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', self.tenant_slug) is not None)
        require(_canonical_uuid(self.installation_id) and _canonical_uuid(self.expected_report_id))
        require(20 <= len(self.secret) <= 200 and 1 <= len(self.request_key) <= 100)
        # to_stdin() also validates UTF-8 encodability and the encoded stdin
        # budget, so construction cannot succeed for a config that could never
        # be delivered. Keep it here; do not move the check to the caller.
        self.to_stdin()

    def __repr__(self):
        return 'PrivateConfig(<redacted>)'

    def to_stdin(self):
        raw = None
        try:
            raw = json.dumps({item.name: getattr(self, item.name) for item in fields(self)},
                             ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        except (ValueError, UnicodeError):
            pass
        require(raw is not None and len(raw) <= CONFIG_LIMIT)
        return raw


def _unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def parse_config(raw):
    require(type(raw) is bytes and len(raw) <= CONFIG_LIMIT)
    value = None
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        pass
    require(type(value) is dict and set(value) == {item.name for item in fields(PrivateConfig)})
    return PrivateConfig(**value)


def _read_private_config(path):
    # Do not resolve/normalize away '..' or symlinks. Pin EACH directory via
    # openat(O_DIRECTORY|O_NOFOLLOW), not lstat-then-open on an absolute parent.
    # Owner/0700 is enforced on the immediate parent only (parity with the
    # existing launcher); intermediate ancestors are pinned with O_NOFOLLOW but
    # their mode is not asserted, so the trusted-host premise still applies.
    supplied = os.fspath(path)
    require(type(supplied) is str and supplied != '' and '\x00' not in supplied)
    require('..' not in supplied.split('/'))
    absolute = Path(os.path.abspath(supplied))
    parts = absolute.parts
    require(len(parts) >= 3)
    directory_fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in parts[1:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        directory = os.fstat(directory_fd)
        require(stat.S_ISDIR(directory.st_mode))
        require(stat.S_IMODE(directory.st_mode) == 0o700 and directory.st_uid == os.getuid())
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600)
            require(info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size <= CONFIG_LIMIT)
            # Bounded even if a same-owner writer grows the file after fstat.
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                raw = handle.read(CONFIG_LIMIT + 1)
            after = os.fstat(fd)
            require((after.st_uid, after.st_mode, after.st_nlink, after.st_size)
                    == (info.st_uid, info.st_mode, info.st_nlink, info.st_size))
            require(len(raw) <= CONFIG_LIMIT)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    return parse_config(raw)


def read_private_config(path):
    result = None
    try:
        result = _read_private_config(path)
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    # Raise outside the handler: no chained OSError filename / JSON secret.
    require(result is not None)
    return result


@dataclass(frozen=True, slots=True)
class DeploymentPermit:
    """Closed administrator input, NOT arbitrary runtime options or proof.

    image_digest is a content digest, not a registry URL or an authenticated
    mapping to a Docker image ID. Runtime verification belongs to later layers.
    """
    image_digest: str
    worker_sha256: str
    receiver_uid: int
    api_uid: int
    api_port: int

    def __post_init__(self):
        # A non-str cannot equal a str constant, so only the digest needs a type
        # check: re.fullmatch raises TypeError on non-str instead of rejecting.
        require(self.worker_sha256 == WORKER_SHA256)
        require(type(self.image_digest) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', self.image_digest) is not None)
        require(type(self.receiver_uid) is int and type(self.api_uid) is int)
        require(0 < self.receiver_uid <= UID_MAX and 0 < self.api_uid <= UID_MAX)
        require(self.receiver_uid != self.api_uid)
        require(type(self.api_port) is int and 1 <= self.api_port <= 65535)

    @classmethod
    def from_mapping(cls, value):
        require(type(value) is dict and set(value) == {item.name for item in fields(cls)})
        return cls(**value)


def validate_binding(config, permit):
    require(type(config) is PrivateConfig and type(permit) is DeploymentPermit)
    host, port = _origin_port(config.origin)
    # The legacy six-field format accepts ::1. This isolation deployment is IPv4.
    require(host == '127.0.0.1' and port == permit.api_port)


def clean_environment():
    """Declare the child environment for I7; nothing is spawned here.

    Returning an empty mapping is the contract, not proof that a child was
    started without inherited secrets.
    """
    return {}


@dataclass(frozen=True, slots=True)
class InfrastructureResult:
    """Only trusted infrastructure observations; never receiver output."""
    status: str

    def __post_init__(self):
        require(type(self.status) is str and self.status in INFRASTRUCTURE_STATUSES)

    def as_dict(self):
        return {'status': self.status}
