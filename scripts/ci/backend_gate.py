"""Fail closed on backend routing and matrix results before receipt verification."""
from __future__ import annotations

import os
import re
from pathlib import Path

FAST_REASONS = frozenset({
    'allowlisted_markdown_only', 'presentation_styles_only', 'presentation_text_only',
    'presentation_only', 'docs_and_presentation_only',
})


def require_backend_result(route_result: str, backend_required: str, route_reason: str,
                           docs_only: str, backend_result: str, backend_groups: str) -> bool:
    """Return whether actual execution receipts must be checked next."""
    if route_result != 'success':
        raise ValueError('backend routing failed, cancelled, skipped or is missing')
    if docs_only not in {'true', 'false'} or not route_reason:
        raise ValueError('backend routing outputs are incomplete')
    if backend_required == 'false':
        if backend_groups != 'skip' or route_reason not in FAST_REASONS:
            raise ValueError('backend shortcut was not explicitly allowlisted')
        if (docs_only == 'true') != (route_reason == 'allowlisted_markdown_only'):
            raise ValueError('docs_only disagrees with the shortcut reason')
        if backend_result != 'skipped':
            raise ValueError('every backend shard must be skipped for the shortcut')
        return False
    if backend_groups == 'basic':
        if docs_only != 'false' or route_reason.removeprefix('preview_basic_') not in FAST_REASONS or not route_reason.startswith('preview_basic_'):
            raise ValueError('basic-only backend route requires an allowlisted preview')
    elif re.fullmatch(r'basic(?:,[a-z_]+)+', backend_groups):
        if docs_only != 'false' or route_reason != 'mapped_modules':
            raise ValueError('selected backend groups require a mapped module route')
    elif backend_groups != 'full':
        raise ValueError('backend group route is missing or invalid')
    if backend_required != 'true' or backend_result != 'success':
        raise ValueError('required backend workers failed, cancelled, skipped or are missing')
    return True


def main() -> int:
    fields = {key: os.environ.get(key, '') for key in (
        'ROUTE_RESULT', 'BACKEND_REQUIRED', 'ROUTE_REASON', 'DOCS_ONLY', 'BACKEND_RESULT', 'BACKEND_GROUPS',
    )}
    try:
        required = require_backend_result(*(fields[key] for key in fields))
    except ValueError as exc:
        print('Backend gate: ' + str(exc))
        return 1
    message = f"Backend gate: route={fields['ROUTE_REASON']}; required={str(required).lower()}; groups={fields['BACKEND_GROUPS']}; matrix={fields['BACKEND_RESULT']}"
    print(message)
    if destination := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(destination).open('a') as stream:
            stream.write(message + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
