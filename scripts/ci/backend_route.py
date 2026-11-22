"""Conservative docs/presentation routing. Execute the PR base version in Actions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

DOC_PATH = re.compile(r'(?:(?:README|README_EN|PROGRESS)\.md|docs/superpowers/(?:specs|plans)/[^/\x00-\x1f\x7f]+\.md)\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
STYLE_PATH = 'frontend/src/pages/public/PublicHomePage.css'
TEXT_PATHS = frozenset(f'frontend/src/locales/{locale}/home.json' for locale in ('zh-CN', 'en-US'))
# These values are rendered as plain text on the public landing page. Business,
# permission, demo/account, navigation and interpolation settings are excluded.
TEXT_KEYS = frozenset({('hero', 'eyebrow'), ('hero', 'title'), ('footer', 'tagline')})
COLOR_PROPERTIES = frozenset({
    'color', 'background-color', 'border-color',
    '--public-home-bg', '--public-home-elevated', '--public-home-text',
    '--public-home-text-secondary', '--public-home-accent', '--public-home-border',
})
DIMENSION_PROPERTIES = frozenset({
    'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'gap', 'border-radius', 'font-size', 'letter-spacing',
})
DECLARATION = re.compile(r'(?m)^([ \t]+)([a-z-]+)([ \t]*:[ \t]*)([^;\n]+)(;[ \t]*)$')
COLOR = re.compile(r'(?:#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})|var\(--public-home-(?:bg|elevated|text|text-secondary|accent|border)\))\Z')
DIMENSION = re.compile(r'(-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))(px|rem|em)?\Z')
PLAIN_TEXT = re.compile(r'[^\x00-\x1f\x7f<>{}\\$]{1,240}\Z')


ROUTING_PROTOCOL = 2

# Versioned migrations with a known business boundary. Any other migration or
# shared migration tooling follows the full fallback.
RUNTIME_MIGRATIONS = (
    r'backend/alembic/versions/(?:20260926_agent_task_core|20260930_agent_readonly_delivery|'
    r'20261001_agent_readonly_controls|20261109_d4_text_delivery|20261113_d4_recovery|'
    r'20261114_r5_(?:d5_basis|d5_proposals|models)|20261115_r5_responses)\.py',
    r'backend/alembic_tenant/versions/(?:tv002_agent_task_core|tv003_agent_readonly_delivery|'
    r'tv004_agent_readonly_controls|tv007_d4_text_delivery|tv008_d4_recovery|tv010_r5_d5_proposals|'
    r'tv011_r5_d5_basis|tv012_r5_models|tv014_r5_responses)\.py',
)

# Only understood surfaces are allowed to narrow CI. Common auth, database
# sessions, infrastructure, shared fixtures and unknown paths match no group.
SOURCE_GROUPS = {
    'receiver': (
        r'sdk/.+', r'deploy/d4-acceptance/.+', r'backend/examples/readonly_d4_text_receiver\.py',
        r'backend/tests/(?:e2e/(?:test_(?:agent|readonly|d4|r5)_\w+|(?:d4_text|sdk_process|agent_local)_\w+)|cli/test_d4_text_\w+)\.py',
    ),
    'runtime': (
        r'backend/app/(?:api|services)/agent/.+\.py',
        r'backend/app/services/agent_runtime/\w+\.py',
        r'backend/app/(?:api|schemas|models)/agent(?:_\w+)?\.py',
        r'backend/app/api/admin/agent_\w+\.py',
        r'backend/app/(?:cli|core)/agent_(?:local_trial|task_attachments)\.py',
        r'backend/app/services/(?:agent_review_skill_service|adoption_audit)\.py',
        r'backend/app/services/(?:capa_agent_(?:capabilities|projection)|capa_current_access|capa_d4_(?:provenance|redaction|text_preview)|capa_d5_(?:measures|proposals)|capa_review_source_guard|fmea_agent_sources)\.py',
        r'backend/app/api/capa(?:_d4_text_preview)?\.py',
        r'backend/app/models/capa_d[45]_\w+\.py',
        r'backend/tests/(?:api/(?:agent/test_\w+|test_(?:admin_agent|agent|d4|readonly|runtime|trial)_\w+)|services/(?:agent|agent_runtime)/\w+)\.py',
        r'backend/tests/test_(?:agent_review_skill|adoption_audit)\w*\.py',
        *RUNTIME_MIGRATIONS,
    ),
    'capa': (
        r'backend/app/(?:api|services|schemas|models)/(?:capa\w*|fmea\w*|scar\w*|iqc\w*|control_plan\w*|cp_sync_\w+|adoption_audit|knowledge_sink_service|graph_projection_service|aql_engine)\.py',
        r'backend/app/state_machines/(?:eightd_state|fmea_state)\.py',
        r'backend/app/services/mes_service\.py',
        r'backend/app/graph/.+\.py',
        r'backend/tests/capa/\w+\.py',
        r'backend/tests/services/test_(?:capa_\w+|knowledge_entry_source)\.py',
        r'backend/tests/test_(?:capa|eightd|d7|adoption_audit)\w*\.py',
    ),
    'tenant': (
        *RUNTIME_MIGRATIONS,
        r'backend/app/services/(?:tenant_schema_diff|tenant_test_rebuild)\.py',
        r'backend/tests/(?:migrations|test_multitenancy)/.+', r'backend/tests/test_migration\w+\.py',
    ),
    'iqc': (
        r'backend/app/(?:api|schemas|services|models)/(?:iqc\w*|scar\w*|aql_engine)\.py',
        r'backend/tests/test_(?:iqc|scar)\w*\.py',
    ),
    'fmea': (
        r'backend/app/(?:api|services|schemas|models)/fmea\w*\.py',
        r'backend/app/state_machines/fmea_state\.py', r'backend/app/graph/.+\.py',
        r'backend/app/services/graph_projection_service\.py', r'backend/app/api/graph\.py',
        r'backend/tests/(?:fmea/.+|test_(?:fmea|dfmea|pfmea|graph|delete_fmea|collaboration)\w*\.py)',
    ),
    'msa': (
        r'backend/app/(?:api|schemas|services|models)/(?:msa\w*|(?:grr|bias|linearity|stability|attribute)(?:_(?:service|engine))?)\.py',
        r'backend/tests/test_msa_service\.py',
    ),
    'spc': (
        r'backend/app/(?:api|schemas|services|models)/spc\w*\.py', r'backend/app/test_spc_engine\.py',
        r'backend/app/services/mes_service\.py',
        r'backend/tests/test_spc\w*\.py',
    ),
    'apqp': (
        r'backend/app/(?:api|schemas|services|models)/apqp(?:_service)?\.py',
        r'backend/tests/test_apqp_service\.py',
    ),
    'ppap': (
        r'backend/app/(?:api|schemas|services|models)/ppap(?:_service)?\.py',
        r'backend/tests/test_ppap_service\.py',
    ),
    'control_plan': (
        r'backend/app/(?:api|schemas|services|models)/(?:control_plan\w*|cp_\w+)\.py',
        r'backend/app/services/cp_validation/.+\.py',
        r'backend/app/services/capa_doc_gate_service\.py',
        r'backend/tests/test_(?:control_plan|cp_)\w*\.py',
    ),
    'integrations': (
        r'backend/app/(?:api|schemas|services|models)/(?:erp\w*|mes\w*|plm\w*|connector_security)\.py',
        r'backend/tests/test_(?:erp|mes|plm|connector_security)\w*\.py',
    ),
}
GROUP_PATHS = {group: tuple(map(re.compile, patterns)) for group, patterns in SOURCE_GROUPS.items()}

def routing(reason: str, paths: list[str], *, docs_only: bool = False, backend_required: bool = True, groups: tuple[str, ...] = ()) -> dict:
    return {'docs_only': docs_only, 'backend_required': backend_required,
            'reason': reason, 'route_reason': reason, 'paths': paths,
            'groups': list(groups) or (['full'] if backend_required else [])}


def changed_entries(raw: bytes) -> list[tuple[str, list[str]]]:
    """Parse complete NUL-delimited name-status output, including both rename ends."""
    if not raw:
        return []
    if not raw.endswith(b'\0'):
        raise ValueError('truncated diff')
    fields = raw[:-1].decode('utf-8', errors='strict').split('\0')
    entries = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if status in {'A', 'D', 'M', 'T'}:
            count = 1
        elif re.fullmatch(r'[RC](?:100|0[0-9]{2})', status):
            count = 2
        else:
            raise ValueError('unsupported diff status')
        changed = fields[index:index + count]
        if len(changed) != count or any(not path for path in changed):
            raise ValueError('incomplete changed paths')
        entries.append((status, changed))
        index += count
    return entries


def classify_diff(raw: bytes) -> dict:
    paths = [path for _, changed in changed_entries(raw) for path in changed]
    if not paths:
        return routing('empty_diff', [])
    docs_only = all(DOC_PATH.fullmatch(path) for path in paths)
    if docs_only:
        return routing('allowlisted_markdown_only', paths, docs_only=True, backend_required=False)
    if all(DOC_PATH.fullmatch(path) or path == STYLE_PATH or path in TEXT_PATHS for path in paths):
        # Paths only establish eligibility. The committed old/new contents must
        # pass the checks below before a frontend change can skip the backend.
        return routing('presentation_content_check_required', paths)
    groups = set()
    for path in paths:
        if DOC_PATH.fullmatch(path):
            continue
        impacted = {group for group, patterns in GROUP_PATHS.items() if any(p.fullmatch(path) for p in patterns)}
        if not impacted:
            return routing('full_backend_required', paths)
        groups.update(impacted)
        if path.startswith('backend/app/models/'):
            groups.add('tenant')
    # Follow shared behavior into consumers, not just the source directory.
    if 'runtime' in groups or 'fmea' in groups:
        groups.update(('receiver', 'capa'))
    if 'fmea' in groups:
        groups.update(('control_plan', 'integrations'))
    if 'spc' in groups:
        groups.update(('msa', 'capa', 'fmea', 'control_plan', 'integrations', 'receiver'))
    if 'iqc' in groups or 'control_plan' in groups:
        groups.add('capa')
    return routing('mapped_modules', paths, groups=('basic', *sorted(groups)))


def safe_dimension(prop: str, value: str) -> bool:
    match = DIMENSION.fullmatch(value)
    if not match:
        return False
    number, unit = float(match[1]), match[2]
    if unit is None:
        return number == 0 and prop != 'font-size'
    if prop == 'font-size':
        low, high = (8, 96) if unit == 'px' else (0.5, 6)
    elif prop == 'letter-spacing':
        low, high = (-2, 8) if unit == 'px' else (-0.1, 0.5)
    else:
        low = 0
        high = (1000 if prop == 'border-radius' else 200) if unit == 'px' else 12
    return low <= number <= high


def style_skeleton(content: str) -> tuple:
    """Mask only existing literal paint/spacing/typography values, never CSS code."""
    parts = []
    previous = 0
    for match in DECLARATION.finditer(content):
        indent, prop, separator, value, ending = match.groups()
        safe = prop in COLOR_PROPERTIES and COLOR.fullmatch(value)
        if prop in DIMENSION_PROPERTIES:
            values = value.split(' ')
            safe = 1 <= len(values) <= 4 and all(safe_dimension(prop, item) for item in values)
            if prop in {'font-size', 'letter-spacing'}:
                safe = safe and len(values) == 1
        elif prop == 'font-weight':
            safe = bool(re.fullmatch(r'(?:[1-8][0-9]{2}|900)', value))
        elif prop == 'line-height':
            safe = bool(re.fullmatch(r'(?:[1-2](?:\.[0-9]+)?|0\.[89][0-9]*|3(?:\.0+)?)', value))
        # Structural tokens prevent a literal replacement string from imitating
        # a masked value. Selectors, rules and unsafe declarations stay exact.
        parts.append(content[previous:match.start()])
        parts.append((indent, prop, separator, ending) if safe else match[0])
        previous = match.end()
    parts.append(content[previous:])
    return tuple(parts)


def display_text_only(before: str, after: str) -> bool:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('non-JSON numeric constant')

    def compare(old, new, path=()):
        if type(old) is not type(new):
            return False
        if isinstance(old, dict):
            return old.keys() == new.keys() and all(compare(old[key], new[key], (*path, key)) for key in old)
        if isinstance(old, list):
            return len(old) == len(new) and all(compare(left, right, (*path, index)) for index, (left, right) in enumerate(zip(old, new)))
        if old == new:
            return True
        return path in TEXT_KEYS and isinstance(old, str) and all(
            text.strip() and PLAIN_TEXT.fullmatch(text) for text in (old, new)
        )

    old = json.loads(before, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    new = json.loads(after, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    return isinstance(old, dict) and isinstance(new, dict) and compare(old, new)


def classify_pr(repo: Path, event_name: str, payload: dict, *, require_preview_receipts: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('invalid event payload')
    pr = payload.get('pull_request', {})
    if not isinstance(pr, dict) or not isinstance(pr.get('base', {}), dict):
        raise ValueError('invalid pull request payload')
    if event_name != 'pull_request' or pr.get('base', {}).get('ref') != 'main':
        return routing('not_main_pull_request', [])
    base, head = pr['base']['sha'], pr['head']['sha']
    if not SHA.fullmatch(base) or not SHA.fullmatch(head):
        raise ValueError('invalid PR revisions')

    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)

    if git('rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValueError('incomplete shallow history')
    for revision in (base, head):
        git('cat-file', '-e', revision + '^{commit}')
    merge_base = git('merge-base', '--all', base, head).decode().splitlines()
    if len(merge_base) != 1 or not SHA.fullmatch(merge_base[0]):
        raise ValueError('missing or ambiguous merge base')
    raw = git('diff', '--no-ext-diff', '--no-textconv', '--name-status', '-z', '--find-renames', merge_base[0], head, '--')
    result = classify_diff(raw)
    if result['groups'] != ['full'] or result['reason'] == 'presentation_content_check_required':
        # Inspect both trees, including the old side of document deletions and
        # renames. Symlinks, executable files and submodules never qualify.
        for revision in (merge_base[0], head):
            entries = git('ls-tree', '-z', revision, '--', *result['paths'])
            if any(entry and entry.split(b'\t', 1)[0].split()[:2] != [b'100644', b'blob'] for entry in entries.split(b'\0')):
                reason = ('non_regular_document' if result['docs_only'] else 'non_regular_presentation'
                          if result['reason'] == 'presentation_content_check_required' else 'non_regular_module')
                result = routing(reason, result['paths'])
                break
    if result['reason'] == 'presentation_content_check_required':
        kinds = set()
        for status, paths in changed_entries(raw):
            path = paths[0]
            if all(DOC_PATH.fullmatch(changed) for changed in paths):
                kinds.add('docs')
                continue
            if status != 'M':
                result = routing('presentation_requires_existing_file_modification', result['paths'])
                break
            before, after = (git('show', f'{revision}:{path}').decode('utf-8', errors='strict') for revision in (merge_base[0], head))
            if path == STYLE_PATH:
                safe = style_skeleton(before) == style_skeleton(after)
                kinds.add('styles')
            else:
                safe = display_text_only(before, after)
                kinds.add('text')
            if not safe:
                result = routing('presentation_content_not_allowlisted', result['paths'])
                break
        else:
            if 'docs' in kinds:
                reason = 'docs_and_presentation_only'
            elif kinds == {'styles'}:
                reason = 'presentation_styles_only'
            elif kinds == {'text'}:
                reason = 'presentation_text_only'
            else:
                reason = 'presentation_only'
            result = routing(reason, result['paths'], backend_required=False)
    if require_preview_receipts and not result['backend_required']:
        result = routing(f'preview_basic_{result["route_reason"]}', result['paths'], groups=('basic',))
    return {**result, 'base_sha': base, 'head_sha': head, 'merge_base': merge_base[0]}


def publish(result: dict) -> None:
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'docs_only={str(result["docs_only"]).lower()}\n')
        output.write(f'backend_required={str(result["backend_required"]).lower()}\n')
        output.write(f'route_reason={result["route_reason"]}\n')
        output.write(f'backend_groups={",".join(result["groups"]) or "skip"}\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('### Backend routing\n\n')
        summary.write('```json\n' + json.dumps(result, ensure_ascii=True, indent=2) + '\n```\n')


def main() -> int:
    if sys.argv[1:] != ['classify']:
        raise ValueError('expected classify command')
    try:
        payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        result = classify_pr(Path.cwd(), os.environ['GITHUB_EVENT_NAME'], payload,
                             require_preview_receipts=os.environ.get('REQUIRE_PREVIEW_RECEIPTS') == 'true')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        publish(routing('classification_error', []))
        return 1
    publish(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
