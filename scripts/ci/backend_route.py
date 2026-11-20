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


def routing(reason: str, paths: list[str], *, docs_only: bool = False, backend_required: bool = True) -> dict:
    return {'docs_only': docs_only, 'backend_required': backend_required,
            'reason': reason, 'route_reason': reason, 'paths': paths}


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
    return routing('full_backend_required', paths)


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
    if require_preview_receipts:
        return routing('preview_receipts_required', [])
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
    if result['reason'] in {'allowlisted_markdown_only', 'presentation_content_check_required'}:
        # Inspect both trees, including the old side of document deletions and
        # renames. Symlinks, executable files and submodules never qualify.
        for revision in (merge_base[0], head):
            entries = git('ls-tree', '-z', revision, '--', *result['paths'])
            if any(entry and entry.split(b'\t', 1)[0].split()[:2] != [b'100644', b'blob'] for entry in entries.split(b'\0')):
                result = routing('non_regular_document' if result['docs_only'] else 'non_regular_presentation', result['paths'])
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
    return {**result, 'base_sha': base, 'head_sha': head, 'merge_base': merge_base[0]}


def publish(result: dict) -> None:
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'docs_only={str(result["docs_only"]).lower()}\n')
        output.write(f'backend_required={str(result["backend_required"]).lower()}\n')
        output.write(f'route_reason={result["route_reason"]}\n')
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
