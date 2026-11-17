"""Conservative docs-only routing. Execute the PR base version in Actions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

DOC_PATH = re.compile(r'(?:(?:README|README_EN|PROGRESS)\.md|docs/superpowers/(?:specs|plans)/[^/\x00-\x1f\x7f]+\.md)\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')


def classify_diff(raw: bytes) -> dict:
    """Parse complete NUL-delimited name-status output, including both rename ends."""
    if not raw:
        return {'docs_only': False, 'reason': 'empty_diff', 'paths': []}
    if not raw.endswith(b'\0'):
        raise ValueError('truncated diff')
    fields = raw[:-1].decode('utf-8', errors='strict').split('\0')
    paths = []
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
        paths.extend(changed)
        index += count
    docs_only = bool(paths) and all(DOC_PATH.fullmatch(path) for path in paths)
    return {'docs_only': docs_only, 'reason': 'allowlisted_markdown_only' if docs_only else 'full_backend_required', 'paths': paths}


def classify_pr(repo: Path, event_name: str, payload: dict) -> dict:
    pr = payload.get('pull_request', {})
    if event_name != 'pull_request' or pr.get('base', {}).get('ref') != 'main':
        return {'docs_only': False, 'reason': 'not_main_pull_request', 'paths': []}
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
    if result['docs_only']:
        # Path suffixes alone cannot prove a file is explanatory Markdown.
        # Inspect both trees, including the old side of deletions and renames.
        for revision in (merge_base[0], head):
            entries = git('ls-tree', '-z', revision, '--', *result['paths'])
            for entry in entries.split(b'\0'):
                if entry and entry.split(b'\t', 1)[0].split()[:2] != [b'100644', b'blob']:
                    result.update(docs_only=False, reason='non_regular_document')
    return {**result, 'base_sha': base, 'head_sha': head, 'merge_base': merge_base[0]}


def publish(result: dict) -> None:
    value = str(result['docs_only']).lower()
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'docs_only={value}\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('### Backend routing\n\n')
        summary.write('```json\n' + json.dumps(result, ensure_ascii=True, indent=2) + '\n```\n')


def main() -> int:
    if sys.argv[1:] != ['classify']:
        raise ValueError('expected classify command')
    try:
        payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        result = classify_pr(Path.cwd(), os.environ['GITHUB_EVENT_NAME'], payload)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        publish({'docs_only': False, 'reason': 'classification_error', 'paths': []})
        return 1
    publish(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
