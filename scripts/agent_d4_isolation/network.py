"""The nftables policy for the shared receiver/API network namespace.

Pure text and pure verification: this module never runs `nft`, never opens a
socket and never looks at a namespace. It decides two things:

* which rules must exist, deterministically, from a validated policy;
* whether a given `nft -j list ruleset` output really is that policy.

The second half matters as much as the first. "The rules were added" is not a
boundary; the boundary is that the *installed* rules still deny everything except
the one allowed tuple, with nothing accepted earlier in the chain.

The policy is keyed on the socket UID the kernel reports, which a process cannot
forge for a packet it sends. Container-internal names and paths are not used.
"""
from dataclasses import dataclass
import json
import re

ID_HEX = re.compile(r'[a-f0-9]{64}')
TABLE = 'oqms4'
CHAIN = 'output'
LOOPBACK = '127.0.0.1'

# Verification outcomes. Fixed strings: they may reach the I6 log chain.
OK = 'ok'
NOT_INSTALLED = 'not_installed'
WRONG_POLICY = 'wrong_policy'
EARLIER_ACCEPT = 'earlier_accept'
UNEXPECTED_ACCEPT = 'unexpected_accept'
MALFORMED = 'malformed'


def _require(condition, message='invalid_policy'):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class NetPolicy:
    """Who may talk to what, inside the dedicated namespace."""
    api_uid: int
    receiver_uid: int
    api_port: int

    def __post_init__(self):
        for value in (self.api_uid, self.receiver_uid):
            _require(type(value) is int and 0 < value < 2 ** 32 - 1)
        _require(self.api_uid != self.receiver_uid)
        _require(type(self.api_port) is int and 0 < self.api_port < 65536)


@dataclass(frozen=True, slots=True)
class Ruleset:
    """The exact statements that must be present, in order."""
    lines: tuple

    def __post_init__(self):
        _require(type(self.lines) is tuple and self.lines)
        _require(all(type(line) is str and line for line in self.lines))

    @property
    def text(self):
        body = '\n'.join('        ' + line for line in self.lines)
        return ('table inet %s {\n    chain %s {\n'
                '        type filter hook output priority 0; policy drop;\n'
                '%s\n    }\n}\n' % (TABLE, CHAIN, body))


def build(policy):
    """The minimal ruleset: one allowed tuple, then an explicit receiver drop.

    `policy drop` already blocks everything unlisted; the explicit receiver drop
    keeps that guarantee visible in the listing, so a later "accept" inserted for
    some other UID cannot silently widen the receiver's path.
    """
    _require(type(policy) is NetPolicy)
    return Ruleset((
        'meta skuid %d ip daddr %s tcp dport %d accept' % (
            policy.receiver_uid, LOOPBACK, policy.api_port),
        'meta skuid %d drop' % policy.receiver_uid,
        'meta skuid %d accept' % policy.api_uid,
    ))


def _rules_in(rules):
    """Flatten each rule's expression list into (comparisons, verdict).

    Real `nft -j list ruleset` emits rules as their own top-level entries, not
    nested inside the chain object, and lists conditions and the verdict as
    separate expressions, for example `[{"match": ...}, {"accept": null}]`.
    """
    pairs = []
    for rule in rules:
        if type(rule) is not dict:
            raise ValueError(MALFORMED)
        comparisons = []
        verdict = None
        for expression in rule.get('expr', []):
            if type(expression) is not dict or len(expression) != 1:
                raise ValueError(MALFORMED)
            key, value = next(iter(expression.items()))
            if key == 'match':
                comparisons.extend(_flatten_match(value))
            elif key in ('accept', 'drop', 'continue', 'return'):
                if verdict is not None:
                    raise ValueError(MALFORMED)
                if key not in ('accept', 'drop'):
                    raise ValueError(MALFORMED)      # only these are understood
                verdict = key
            else:
                raise ValueError(MALFORMED)
        if verdict is None:
            raise ValueError(MALFORMED)
        pairs.append((tuple(comparisons), verdict))
    return pairs


def _flatten_match(match):
    """One comparison as a comparable `field=value` string."""
    if type(match) is not dict or match.get('op') != '==':
        raise ValueError(MALFORMED)
    return (_render(match.get('left')) + '=' + _render(match.get('right')),)


def _render(node):
    if type(node) is str:
        return node
    if type(node) is int:
        return str(node)
    if type(node) is not dict or len(node) != 1:
        raise ValueError(MALFORMED)
    key, value = next(iter(node.items()))
    if key == 'meta':
        return 'meta ' + value.get('key', '?')
    if key == 'payload':
        return value.get('protocol', '?') + '.' + value.get('field', '?')
    if key == 'match':
        return '(' + ','.join(_flatten_match(value)) + ')'
    raise ValueError(MALFORMED)


@dataclass(frozen=True, slots=True)
class Verification:
    ok: bool
    reason: str

    def __post_init__(self):
        _require(type(self.ok) is bool)
        _require(self.reason in (OK, NOT_INSTALLED, WRONG_POLICY, EARLIER_ACCEPT,
                                 UNEXPECTED_ACCEPT, MALFORMED))
        _require((self.reason == OK) == self.ok)


def verify(policy, listing):
    """Check an `nft -j list ruleset` document against the policy.

    Rejects: missing table/chain, a policy other than drop, an accept that
    precedes the receiver's allowed tuple, any accept other than the exact
    expected ones, and any rule whose shape is not understood.
    """
    _require(type(policy) is NetPolicy)
    _require(type(listing) is dict and 'nftables' in listing)
    entries = listing['nftables']
    if type(entries) is not list:
        raise ValueError(MALFORMED)
    table = None
    for entry in entries:
        if type(entry) is not dict:
            raise ValueError(MALFORMED)
        candidate = entry.get('table')
        if type(candidate) is dict and candidate.get('name') == TABLE:
            if candidate.get('family') != 'inet':
                return Verification(False, WRONG_POLICY)
            table = candidate
    if table is None:
        return Verification(False, NOT_INSTALLED)
    chain = None
    for entry in entries:
        if type(entry) is dict and type(entry.get('chain')) is dict \
                and entry['chain'].get('name') == CHAIN:
            chain = entry['chain']
    if chain is None:
        return Verification(False, NOT_INSTALLED)
    if chain.get('policy') != 'drop':
        return Verification(False, WRONG_POLICY)

    rules = []
    for entry in entries:
        rule = entry.get('rule') if type(entry) is dict else None
        if type(rule) is dict and rule.get('table') == TABLE and rule.get('chain') == CHAIN:
            rules.append(rule)
    expected = _rules_in(rules)
    wanted_first = ('meta skuid=%d' % policy.receiver_uid,
                    'ip.daddr=%s' % LOOPBACK,
                    'tcp.dport=%d' % policy.api_port)
    wanted_drop = ('meta skuid=%d' % policy.receiver_uid,)
    wanted_api = ('meta skuid=%d' % policy.api_uid,)

    seen_receiver_allow = False
    seen_receiver_drop = False
    for index, (matches, verdict) in enumerate(expected):
        if verdict == 'accept':
            if matches == wanted_first:
                seen_receiver_allow = True
                continue
            if matches == wanted_api:
                if not seen_receiver_allow:
                    # The API's blanket accept is harmless in itself, but an
                    # accept placed before the receiver tuple could shadow it.
                    return Verification(False, EARLIER_ACCEPT)
                continue
            if _is_broadening_of(matches, wanted_first):
                # A prefix of the allowed tuple accepts strictly more traffic.
                return Verification(False, EARLIER_ACCEPT)
            return Verification(False, UNEXPECTED_ACCEPT)
        if verdict == 'drop' and matches == wanted_drop:
            if not seen_receiver_allow:
                return Verification(False, EARLIER_ACCEPT)
            seen_receiver_drop = True
            continue
        return Verification(False, UNEXPECTED_ACCEPT)

    if not seen_receiver_allow or not seen_receiver_drop:
        return Verification(False, WRONG_POLICY)
    return Verification(True, OK)


def _is_broadening_of(matches, wanted):
    return bool(matches) and len(matches) < len(wanted) and wanted[:len(matches)] == matches


def parse_listing(raw):
    """Strict JSON parse of nft's output; duplicate keys are corruption."""
    _require(type(raw) is bytes or type(raw) is str)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(MALFORMED)
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError(MALFORMED) from None
    if type(value) is not dict:
        raise ValueError(MALFORMED)
    return value
