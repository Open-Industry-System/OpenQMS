"""Canonical connector destinations and deployment-controlled ERP egress."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


def canonical_origin(url: str) -> str:
    """Strict HTTP origin: reject ambiguous authorities and URL credentials."""
    if not isinstance(url, str) or not url or any(ord(c) <= 32 for c in url) or '\\' in url:
        raise ValueError('Invalid connector URL')
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError('Connector URL must be HTTP(S) without userinfo')
    if parts.query or parts.fragment or '%' in parts.netloc:
        raise ValueError('Connector URL cannot contain query, fragment, or encoded authority')
    host = parts.hostname.encode('idna').decode('ascii').lower()
    if host.endswith('.'):
        host = host[:-1]
    if not host:
        raise ValueError('Invalid connector host')
    # Disallow legacy IPv4 spellings (e.g. decimal, octal, hexadecimal).
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if all(c in '0123456789.' for c in host) or host.startswith('0x'):
            raise ValueError('Non-canonical connector IP address')
    else:
        host = address.compressed
    authority = f'[{host}]' if ':' in host else host
    if parts.port == 0:
        raise ValueError('Connector port must be between 1 and 65535')
    port = parts.port if parts.port is not None else (443 if parts.scheme == 'https' else 80)
    return f'{parts.scheme}://{authority}:{port}'


def validate_endpoint_path(path: str) -> str:
    """Static endpoint paths carry no authority, query, encoding or traversal."""
    if (not path.startswith('/') or path.startswith('//') or
            any(c in path for c in ('?', '#', '\\', '%')) or
            any(ord(c) <= 32 for c in path) or
            any(segment in ('.', '..') for segment in path.split('/'))):
        raise ValueError('Endpoint must be a credential-free relative path')
    return path


def credential_context(config: dict) -> str:
    return f"rest|{config.get('auth_type', 'none')}|{canonical_origin(config.get('base_url', ''))}"


async def pinned_erp_destination(base_url: str, path: str) -> tuple[str, str, str]:
    """Resolve once, validate every answer, then use a literal IP (also on retries).

    Each exact origin needs explicit CIDRs supplied by the deployment, not by
    module approvers. Private manufacturing networks are supported deliberately.
    """
    from app.config import settings

    origin = canonical_origin(base_url)
    validate_endpoint_path(urlsplit(base_url).path or '/')
    validate_endpoint_path(path)
    policy = settings.ERP_ALLOWED_ORIGINS
    # Canonicalize deployment keys too, so default ports need not be written.
    allowed = next((networks for configured, networks in policy.items()
                    if canonical_origin(configured) == origin), None)
    if not allowed:
        raise ValueError('ERP origin is not approved by the deployment allowlist')
    networks = [ipaddress.ip_network(value, strict=True) for value in allowed]
    parts = urlsplit(origin)
    host = parts.hostname
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        answers = await asyncio.get_running_loop().getaddrinfo(host, parts.port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(ipaddress.ip_address(answer[4][0]) for answer in answers))
    if not addresses or any(not any(address in network for network in networks) for address in addresses):
        raise ValueError('ERP resolved address is outside approved networks')
    # These are never useful integration destinations, even under broad CIDRs.
    effective_addresses = [getattr(address, "ipv4_mapped", None) or address for address in addresses]
    if any(address.is_unspecified or address.is_multicast or address.is_link_local or address.is_loopback for address in effective_addresses):
        raise ValueError('ERP resolved address is an unsafe infrastructure address')
    address = addresses[0]
    ip_host = f'[{address}]' if address.version == 6 else str(address)
    default_port = 443 if parts.scheme == 'https' else 80
    suffix = '' if parts.port == default_port else f':{parts.port}'
    authority = f'[{host}]' if ':' in host else host
    target_path = urlsplit(base_url).path.rstrip('/') + path
    url = urlunsplit((parts.scheme, f'{ip_host}{suffix}', target_path, '', ''))
    return url, f'{authority}{suffix}', host
