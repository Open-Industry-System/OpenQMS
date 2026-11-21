"""Fail closed on backend routing and matrix results before receipt verification."""
from __future__ import annotations

import os
from pathlib import Path

FAST_REASONS = frozenset({
    'allowlisted_markdown_only', 'presentation_styles_only', 'presentation_text_only',
    'presentation_only', 'docs_and_presentation_only',
})


def require_backend_result(route_result: str, backend_required: str, route_reason: str,
                           docs_only: str, backend_result: str) -> bool:
    """Return whether two actual execution receipts must be checked next."""
    if route_result != 'success':
        raise ValueError('backend routing failed, cancelled, skipped or is missing')
    if docs_only not in {'true', 'false'} or not route_reason:
        raise ValueError('backend routing outputs are incomplete')
    if backend_required == 'false':
        if route_reason not in FAST_REASONS:
            raise ValueError('backend shortcut was not explicitly allowlisted')
        if (docs_only == 'true') != (route_reason == 'allowlisted_markdown_only'):
            raise ValueError('docs_only disagrees with the shortcut reason')
        if backend_result != 'skipped':
            raise ValueError('every backend shard must be skipped for the shortcut')
        return False
    if backend_required != 'true' or backend_result != 'success':
        raise ValueError('required backend shards failed, cancelled, skipped or are missing')
    return True


def main() -> int:
    fields = {key: os.environ.get(key, '') for key in (
        'ROUTE_RESULT', 'BACKEND_REQUIRED', 'ROUTE_REASON', 'DOCS_ONLY', 'BACKEND_RESULT',
    )}
    try:
        full = require_backend_result(*(fields[key] for key in fields))
    except ValueError as exc:
        print('Backend gate: ' + str(exc))
        return 1
    message = f"Backend gate: route={fields['ROUTE_REASON']}; full={str(full).lower()}; matrix={fields['BACKEND_RESULT']}"
    print(message)
    if destination := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(destination).open('a') as stream:
            stream.write(message + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
