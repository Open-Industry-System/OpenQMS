"""Pure routing tests against real committed PR histories, without a database."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/ci/backend_route.py'
STYLE = 'frontend/src/pages/public/PublicHomePage.css'
ZH_TEXT = 'frontend/src/locales/zh-CN/home.json'
EN_TEXT = 'frontend/src/locales/en-US/home.json'


def load_route():
    spec = importlib.util.spec_from_file_location('backend_route', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('raw, expected', [
    (b'M\0docs/superpowers/specs/r6.md\0A\0docs/superpowers/plans/r6.md\0M\0PROGRESS.md\0', True),
    (b'M\0PROGRESS.md\0M\0backend/app/main.py\0', False),
    (b'D\0backend/app/main.py\0', False),
    (b'R100\0backend/app/main.py\0docs/superpowers/specs/code.md\0', False),
    (b'M\0.github/workflows/test.yml\0', False),
    (b'M\0scripts/ci/backend_route.py\0', False),
    (b'M\0backend/tests/ci/test_backend_fast_path.py\0', False),
    (b'M\0docs/e2e.md\0', False),
    (b'M\0README.md\0M\0README_EN.md\0', True),
    (b'M\0README_EN.md\0M\0backend/app/main.py\0', False),
    (b'M\0backend/README.md\0', False),
    (b'M\0docs/superpowers/specs/nested/a.md\0', False),
    (b'D\0docs/superpowers/plans/old.md\0', True),
    (b'R087\0docs/superpowers/specs/old.md\0docs/superpowers/plans/new.md\0', True),
    (b'', False),
])
def test_complete_change_classification(raw, expected):
    result = load_route().classify_diff(raw)
    assert result['docs_only'] is expected
    assert result['backend_required'] is not expected


@pytest.mark.parametrize('path', [STYLE, ZH_TEXT, EN_TEXT])
def test_frontend_path_alone_never_authorizes_skip(path):
    result = load_route().classify_diff(f'M\0{path}\0'.encode())
    assert result['backend_required'] is True
    assert result['reason'] == 'presentation_content_check_required'


@pytest.mark.parametrize('raw', [b'M\0PROGRESS.md', b'R100\0PROGRESS.md\0', b'X\0PROGRESS.md\0', b'M\0\0', b'M\0\xff\0'])
def test_incomplete_diff_is_an_error(raw):
    with pytest.raises(ValueError):
        load_route().classify_diff(raw)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args]).decode().strip()


def commit(repository, message='change'):
    git(repository, 'add', '.')
    git(repository, 'commit', '-qm', message)
    return git(repository, 'rev-parse', 'HEAD')


def write(repository, path, text):
    destination = repository / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text)


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.email', 'ci-test@example.invalid')
    git(tmp_path, 'config', 'user.name', 'CI test')
    write(tmp_path, 'PROGRESS.md', 'base')
    commit(tmp_path, 'base')
    return tmp_path


@pytest.fixture
def presentation_repository(repository):
    # Use real consumed resources, rather than an invented unused fast-path file.
    for path in (STYLE, ZH_TEXT, EN_TEXT):
        write(repository, path, (ROOT / path).read_text())
    write(repository, 'backend/app/main.py', 'print(1)\n')
    commit(repository, 'existing presentation resources')
    return repository


def event(base, head):
    return {'pull_request': {'base': {'ref': 'main', 'sha': base}, 'head': {'sha': head}}}


def classify(repository, base):
    head = git(repository, 'rev-parse', 'HEAD')
    return load_route().classify_pr(repository, 'pull_request', event(base, head))


def replace(repository, path, old, new):
    content = (repository / path).read_text()
    assert old in content
    (repository / path).write_text(content.replace(old, new, 1))


def edit_text(repository, path=ZH_TEXT, keys=('hero', 'title'), value='让质量数据帮助工程师。'):
    content = json.loads((repository / path).read_text())
    target = content
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    (repository / path).write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')


@pytest.mark.parametrize('scenario, reason', [
    ('style', 'presentation_styles_only'),
    ('zh-text', 'presentation_text_only'),
    ('en-text', 'presentation_text_only'),
    ('style-and-text', 'presentation_only'),
    ('docs-and-text', 'docs_and_presentation_only'),
])
def test_low_risk_presentation_changes_skip_backend(presentation_repository, scenario, reason):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    if scenario in {'style', 'style-and-text'}:
        replace(repo, STYLE, 'gap: 32px;', 'gap: 36px;')
    if scenario in {'zh-text', 'style-and-text', 'docs-and-text'}:
        edit_text(repo)
    if scenario == 'en-text':
        edit_text(repo, EN_TEXT, ('footer', 'tagline'), 'Quality management for every manufacturing team')
    if scenario == 'docs-and-text':
        write(repo, 'PROGRESS.md', 'Updated public landing-page wording')
    commit(repo)
    result = classify(repo, base)
    assert result['backend_required'] is False
    assert result['docs_only'] is False
    assert result['route_reason'] == reason


@pytest.mark.parametrize('old, new', [
    ('gap: 32px;', 'gap: var(--permission-hidden);'),
    ('display: flex;', 'display: none;'),
    ('position: sticky;', 'position: fixed;'),
    ('.public-home__brand {', '.protected-route {'),
    ('content: "";', 'content: "Permission granted";'),
    ('gap: 32px;', 'gap: 32px; background: url(https://example.invalid/track);'),
    ('gap: 32px;', 'gap: 32px !important;'),
    ('gap: 32px;', 'gap: expression(alert(1));'),
    ('gap: 32px;', 'gap: 36px;\n  visibility: hidden;'),
    ('gap: 32px;', 'gap: 36px;\n  /* changed CSS code */'),
    ('gap: 32px;', 'gap: <presentation-value>;'),
    ('gap: 32px;', 'gap: -10000px;'),
    ('font-size: 1.3rem;', 'font-size: 0;'),
    ('line-height: 1.4;', 'line-height: 0.0;'),
    ('--public-home-text: #e7f7f5;', '--public-home-text: #e7f7f500;'),
    ('--public-home-text: #e7f7f5;', '--public-home-text: transparent;'),
])
def test_css_code_and_behavior_changes_require_backend(presentation_repository, old, new):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    replace(repo, STYLE, old, new)
    commit(repo)
    result = classify(repo, base)
    assert result['backend_required'] is True
    assert result['route_reason'] == 'presentation_content_not_allowlisted'


@pytest.mark.parametrize('old, new', [
    ('--public-home-accent: #38d4b8;', '--public-home-accent: #40dcbf;'),
    ('font-size: 1.3rem;', 'font-size: 1.4rem;'),
    ('font-weight: 760;', 'font-weight: 740;'),
    ('line-height: 1.4;', 'line-height: 1.5;'),
    ('padding: 9px 16px;', 'padding: 10px 18px;'),
])
def test_bounded_existing_style_values_are_useful_fast_paths(presentation_repository, old, new):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    replace(repo, STYLE, old, new)
    commit(repo)
    assert classify(repo, base)['backend_required'] is False


@pytest.mark.parametrize('keys, value', [
    (('nav', 'enterSystem'), 'Administrators only'),
    (('hero', 'demo'), 'Write to the production database'),
    (('ai', 'principle'), 'Skip human permission review'),
    (('architecture', 'stack'), ['React', 'New API']),
    (('hero', 'title'), '{{permission}}'),
    (('hero', 'title'), '$t(login:password)'),
    (('hero', 'title'), '<script>execute()</script>'),
    (('hero', 'title'), 'bad\ncontrol'),
    (('hero', 'title'), ''),
    (('hero', 'title'), 123),
    (('hero', 'title'), 'x' * 241),
    (('permissions',), {'admin': True}),
])
def test_business_or_structural_text_changes_require_backend(presentation_repository, keys, value):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    edit_text(repo, keys=keys, value=value)
    commit(repo)
    assert classify(repo, base)['backend_required'] is True


@pytest.mark.parametrize('path', [
    'frontend/src/pages/public/PublicHomePage.tsx',
    'frontend/src/components/ProtectedRoute.tsx',
    'frontend/src/api/auth.ts',
    'frontend/src/locales/zh-CN/users.json',
    'frontend/src/config/publicDemo.ts',
    'frontend/src/styles/design-system.css',
    'backend/app/main.py', 'backend/alembic/versions/new.py',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.ts',
    'frontend/src/pages/public/PublicHomePage.test.tsx',
    '.github/workflows/test.yml', 'Makefile', 'backend/pytest.ini',
])
def test_mixed_changes_do_not_inherit_frontend_shortcut(presentation_repository, path):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    edit_text(repo)
    write(repo, path, 'changed behavior or configuration')
    commit(repo)
    assert classify(repo, base)['backend_required'] is True


def test_all_commits_and_real_rename_are_included(repository):
    base = git(repository, 'rev-parse', 'HEAD')
    write(repository, 'source.py', 'print(1)')
    commit(repository, 'code')
    write(repository, 'PROGRESS.md', 'updated')
    head = commit(repository, 'docs')
    assert classify(repository, base)['backend_required'] is True
    base = head
    destination = 'docs/superpowers/specs/code.md'
    (repository / destination).parent.mkdir(parents=True)
    git(repository, 'mv', 'source.py', destination)
    commit(repository, 'rename')
    result = classify(repository, base)
    assert result['paths'] == ['source.py', destination]
    assert result['backend_required'] is True


@pytest.mark.parametrize('scenario', ['delete', 'rename', 'add', 'doc-to-resource', 'mode', 'symlink'])
def test_presentation_file_identity_changes_require_backend(presentation_repository, scenario):
    repo = presentation_repository
    if scenario in {'add', 'doc-to-resource'}:
        git(repo, 'rm', ZH_TEXT)
        if scenario == 'doc-to-resource':
            write(repo, 'docs/superpowers/specs/text.md', (ROOT / ZH_TEXT).read_text())
        commit(repo, 'prepare identity change')
    base = git(repo, 'rev-parse', 'HEAD')
    if scenario == 'delete':
        git(repo, 'rm', ZH_TEXT)
    elif scenario == 'rename':
        git(repo, 'mv', ZH_TEXT, 'frontend/src/locales/zh-CN/unused.json')
    elif scenario == 'add':
        write(repo, ZH_TEXT, (ROOT / ZH_TEXT).read_text())
    elif scenario == 'doc-to-resource':
        (repo / ZH_TEXT).parent.mkdir(parents=True, exist_ok=True)
        git(repo, 'mv', 'docs/superpowers/specs/text.md', ZH_TEXT)
    elif scenario == 'mode':
        (repo / ZH_TEXT).chmod(0o755)
    else:
        (repo / ZH_TEXT).unlink()
        (repo / ZH_TEXT).symlink_to('users.json')
    commit(repo)
    assert classify(repo, base)['backend_required'] is True


def test_docs_remain_eligible_for_add_delete_and_rename(repository):
    base = git(repository, 'rev-parse', 'HEAD')
    write(repository, 'README.md', 'Overview')
    write(repository, 'docs/superpowers/specs/new.md', 'Spec')
    git(repository, 'rm', 'PROGRESS.md')
    commit(repository)
    result = classify(repository, base)
    assert result['docs_only'] is True
    assert result['backend_required'] is False
    assert result['route_reason'] == 'allowlisted_markdown_only'
    base = git(repository, 'rev-parse', 'HEAD')
    git(repository, 'mv', 'README.md', 'README_EN.md')
    commit(repository)
    assert classify(repository, base)['backend_required'] is False


def test_symlink_markdown_is_not_explanatory_document(repository):
    base = git(repository, 'rev-parse', 'HEAD')
    link = repository / 'docs/superpowers/specs/link.md'
    link.parent.mkdir(parents=True)
    link.symlink_to('../../../source.py')
    commit(repository)
    result = classify(repository, base)
    assert result['backend_required'] is True
    assert result['docs_only'] is False


def test_pr_uses_merge_base_instead_of_newer_target_tip(presentation_repository):
    repo = presentation_repository
    initial = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', '-qb', 'pr')
    write(repo, 'backend/app/main.py', 'print(2)\n')
    head = commit(repo, 'PR backend change')
    git(repo, 'checkout', '-qb', 'target-main', initial)
    # A newer main independently contains the same backend contents. A base/head
    # two-dot diff would hide the backend change that this PR actually contains.
    write(repo, 'backend/app/main.py', 'print(2)\n')
    base = commit(repo, 'main independent change')
    git(repo, 'checkout', 'pr')
    edit_text(repo)
    head = commit(repo, 'PR display change')
    result = load_route().classify_pr(repo, 'pull_request', event(base, head))
    assert result['merge_base'] == initial
    assert 'backend/app/main.py' in result['paths']
    assert result['backend_required'] is True


@pytest.mark.parametrize('scenario', ['missing-commit', 'invalid-json', 'duplicate-key', 'non-json-number', 'invalid-utf8'])
def test_classification_errors_publish_full_and_fail(presentation_repository, tmp_path, scenario):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    if scenario == 'invalid-json':
        write(repo, ZH_TEXT, '{bad json}')
    elif scenario == 'duplicate-key':
        write(repo, ZH_TEXT, '{"hero": {}, "hero": {"title": "new"}}')
    elif scenario == 'non-json-number':
        write(repo, ZH_TEXT, '{"hero": NaN}')
    elif scenario == 'invalid-utf8':
        (repo / STYLE).write_bytes(b'\xff')
    else:
        edit_text(repo)
    head = commit(repo)
    if scenario == 'missing-commit':
        head = 'b' * 40
    payload = tmp_path / 'event.json'
    payload.write_text(json.dumps(event(base, head)))
    output, summary = tmp_path / 'output', tmp_path / 'summary'
    result = subprocess.run([sys.executable, str(SCRIPT), 'classify'], cwd=repo, env={
        **os.environ, 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': str(payload),
        'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
        'REQUIRE_PREVIEW_RECEIPTS': 'false',
    }, capture_output=True, text=True)
    assert result.returncode == 1
    assert output.read_text() == 'docs_only=false\nbackend_required=true\nroute_reason=classification_error\n'
    assert 'classification_error' in summary.read_text()


def test_main_push_other_base_and_preview_never_shortcut(presentation_repository):
    repo = presentation_repository
    route = load_route()
    assert route.classify_pr(repo, 'push', {})['backend_required'] is True
    assert route.classify_pr(repo, 'pull_request', {'pull_request': {'base': {'ref': 'develop'}}})['backend_required'] is True
    base = git(repo, 'rev-parse', 'HEAD')
    edit_text(repo)
    head = commit(repo)
    result = route.classify_pr(repo, 'pull_request', event(base, head), require_preview_receipts=True)
    assert result['backend_required'] is True
    assert result['route_reason'] == 'preview_receipts_required'


def test_legitimate_skip_publishes_explicit_reason(presentation_repository, tmp_path):
    repo = presentation_repository
    base = git(repo, 'rev-parse', 'HEAD')
    edit_text(repo)
    head = commit(repo)
    payload, output, summary = (tmp_path / name for name in ('event.json', 'output', 'summary'))
    payload.write_text(json.dumps(event(base, head)))
    result = subprocess.run([sys.executable, str(SCRIPT), 'classify'], cwd=repo, env={
        **os.environ, 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': str(payload),
        'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
        'REQUIRE_PREVIEW_RECEIPTS': 'false',
    }, capture_output=True, text=True)
    assert result.returncode == 0
    assert output.read_text() == 'docs_only=false\nbackend_required=false\nroute_reason=presentation_text_only\n'
    assert 'presentation_text_only' in summary.read_text()
