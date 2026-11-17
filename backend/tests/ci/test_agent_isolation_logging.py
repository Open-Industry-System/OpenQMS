"""The isolated API's logging policy must never copy attacker-controlled text."""
import io
import logging
import sys
import warnings

import pytest

from app.core import agent_isolation_logging as policy

SECRET = 'sk-live-SENTINEL-0123456789abcdef'


@pytest.fixture(autouse=True)
def clean_logging():
    """Install the policy, then restore the previous logging state."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level, logging.lastResort,
             logging.raiseExceptions, sys.excepthook, sys.unraisablehook,
             warnings.showwarning)
    try:
        policy.install()
        yield
    finally:
        handlers, level, last_resort, raise_exc, excepthook, unraisable, warn = saved
        root.handlers = handlers
        root.setLevel(level)
        logging.lastResort = last_resort
        logging.raiseExceptions = raise_exc
        sys.excepthook = excepthook
        sys.unraisablehook = unraisable
        warnings.showwarning = warn


def capture():
    stream = io.StringIO()
    logging.getLogger().handlers[0].setStream(stream)
    return stream


def test_a_secret_in_a_message_never_reaches_the_handler():
    stream = capture()
    logging.getLogger('app.api').error('GET /x?token=' + SECRET)
    assert SECRET not in stream.getvalue()
    assert 'unknown_event' in stream.getvalue()


def test_a_secret_in_an_exception_never_reaches_the_handler():
    stream = capture()
    try:
        raise RuntimeError('failed with ' + SECRET)
    except RuntimeError:
        logging.getLogger('app.api').exception('boom')
    out = stream.getvalue()
    assert SECRET not in out
    assert 'Traceback' not in out
    assert 'unhandled' in out


def test_a_secret_in_extra_is_dropped():
    stream = capture()
    logging.getLogger('app.api').error('x', extra={'token': SECRET, 'path': '/' + SECRET})
    assert SECRET not in stream.getvalue()


def test_extra_fields_are_removed_from_the_record_itself():
    """Not just hidden from the formatter: they must not exist on the record."""
    seen = {}

    class Late(logging.Handler):
        def emit(self, record):
            seen.update(record.__dict__)

    late = Late()
    logging.getLogger().addHandler(late)
    try:
        logging.getLogger('app.api').error('x', extra={'token': SECRET, 'path': '/' + SECRET})
    finally:
        logging.getLogger().removeHandler(late)
    assert 'token' not in seen and 'path' not in seen
    assert SECRET not in repr(seen)


def test_known_route_and_event_are_kept():
    stream = capture()
    logging.getLogger('app.api').info('', extra=policy.safe_extra(policy.REQUEST, 'claim'))
    line = stream.getvalue()
    assert 'request' in line and 'claim' in line


def test_unknown_route_becomes_a_placeholder():
    stream = capture()
    logging.getLogger('app.api').warning('', extra=policy.safe_extra(policy.REQUEST, SECRET))
    line = stream.getvalue()
    assert SECRET not in line
    assert 'unknown_event' in line or 'request' in line
    assert '-' in line


def test_excepthook_and_unraisablehook_emit_without_text():
    stream = capture()
    try:
        raise ValueError(SECRET)
    except ValueError:
        sys.excepthook(*sys.exc_info())
    sys.unraisablehook(type('U', (Exception,), {})(SECRET))
    out = stream.getvalue()
    assert SECRET not in out
    assert out.count('unhandled') >= 2


def test_warnings_do_not_carry_their_message():
    stream = capture()
    warnings.warn('careful: ' + SECRET)
    out = stream.getvalue()
    assert SECRET not in out


def test_last_resort_is_disabled_so_nothing_escapes_to_stderr():
    assert logging.lastResort is None
    assert logging.raiseExceptions is False


def test_preexisting_handlers_are_replaced_not_reformatted(capsys):
    """A handler installed before install() must not keep the raw record."""
    logging.getLogger().handlers = [logging.StreamHandler(sys.stdout)]
    policy.install()
    logging.getLogger('app.api').error('leak ' + SECRET)
    captured = capsys.readouterr()
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_a_handler_added_after_install_still_receives_safe_records():
    """The DB handler is attached during lifespan, i.e. after install()."""
    captured = []

    class Late(logging.Handler):
        def emit(self, record):
            captured.append((record.getMessage(), record.exc_text, self.format(record)))

    late = Late()
    late.setFormatter(policy.SafeFormatter())
    logging.getLogger().addHandler(late)
    try:
        try:
            raise RuntimeError('failed with ' + SECRET)
        except RuntimeError:
            logging.getLogger('app.api').exception('boom ' + SECRET)
    finally:
        logging.getLogger().removeHandler(late)
    joined = repr(captured)
    assert SECRET not in joined
    assert captured, 'the late handler received nothing'
    message, exc_text, formatted = captured[0]
    assert SECRET not in message and exc_text is None and SECRET not in formatted


def test_the_isolated_api_entry_installs_the_policy_before_importing_the_app():
    """Line numbers only: the module-level import graph is not executed here."""
    import ast
    from pathlib import Path
    source = Path('scripts/agent_d4_isolated_api.py').read_text()
    tree = ast.parse(source)
    install_lines = []
    app_import_lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == 'install':
            install_lines.append(node.lineno)
        if isinstance(node, ast.ImportFrom) and node.module == 'app.main':
            app_import_lines.append(node.lineno)
    assert install_lines, 'the policy is never installed'
    assert app_import_lines, 'the app is never imported'
    assert min(install_lines) < min(app_import_lines), \
        'the app is imported before the policy is installed'
    # Only the function body may import the app: no module-level import sneaks in.
    module_level = [n.lineno for n in tree.body
                    if isinstance(n, ast.ImportFrom) and n.module == 'app.main']
    assert module_level == [], module_level
