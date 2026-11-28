"""Logging policy for the isolated D4 API process.

The receiver is untrusted, and it can put a secret anywhere it controls: the
request target, a query string, a header, a body, a malformed HTTP frame, or an
exception message. This module is installed *before* the application is imported
and before the HTTP parser starts, so nothing it says can reach a handler that
was configured earlier.

What is allowed out is deliberately tiny: a fixed event code, a fixed route
identifier chosen from a closed set, a level and a timestamp. Nothing derived
from the request is ever formatted. Unknown routes and parse failures get fixed
placeholders, not the path that caused them.

This is not a claim that the receiver cannot signal through timing or connection
behaviour; it only bounds what the log chain may contain.
"""
import logging
import sys
import warnings

# Closed set of events. Anything not listed is replaced by UNKNOWN_EVENT.
REQUEST = 'request'
UNKNOWN_ROUTE = 'unknown_route'
PARSE_FAILURE = 'parse_failure'
UNHANDLED = 'unhandled'
BACKGROUND = 'background'
STARTUP = 'startup'
SHUTDOWN = 'shutdown'
UNKNOWN_EVENT = 'unknown_event'

EVENTS = frozenset((REQUEST, UNKNOWN_ROUTE, PARSE_FAILURE, UNHANDLED,
                    BACKGROUND, STARTUP, SHUTDOWN, UNKNOWN_EVENT))

# Routes the isolated API may actually serve. Anything else is unknown_route.
ROUTES = frozenset((
    'claim',
    'heartbeat',
    'deliver',
    'ack',
    'finish',
    'status',
))

PLACEHOLDER = '-'

# Field names the policy is willing to emit. Anything else is dropped.
FIELDS = ('event', 'route', 'level', 'logger', 'time')

_SAFE_LOGGERS = ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'app', 'asgi')


class SafeRecord(logging.LogRecord):
    """A record with no attacker-derived text at all."""

    def getMessage(self):                      # noqa: N802 - logging API
        return '%s %s' % (getattr(self, 'event', UNKNOWN_EVENT),
                          getattr(self, 'route', PLACEHOLDER))


def _safe_logger(name):
    """Map any logger name onto the closed set; unknown names lose detail."""
    for prefix in _SAFE_LOGGERS:
        if name == prefix or name.startswith(prefix + '.'):
            return prefix
    return 'other'


class PolicyFilter(logging.Filter):
    """Rewrite every record into the fixed shape, dropping the original text.

    The original message, arguments, exception info, stack info and any `extra`
    fields are discarded rather than redacted: a redactor can miss an encoding,
    while a closed allowlist cannot leak what it never copies.
    """

    def filter(self, record):
        event = getattr(record, 'event', None)
        if event not in EVENTS:
            # Classify without copying text: an exception record is `unhandled`,
            # anything else is `unknown_event`.
            event = UNHANDLED if record.exc_info else UNKNOWN_EVENT
        route = getattr(record, 'route', None)
        if route not in ROUTES:
            route = PLACEHOLDER
        record.msg = '%s %s' % (event, route)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        record.event = event
        record.route = route
        record.logger_safe = _safe_logger(record.name)
        for key in list(record.__dict__):
            if key not in ('name', 'levelno', 'levelname', 'pathname', 'lineno',
                           'msg', 'args', 'exc_info', 'exc_text', 'stack_info',
                           'created', 'msecs', 'relativeCreated', 'thread',
                           'threadName', 'process', 'processName', 'funcName',
                           'module', 'filename', 'event', 'route', 'logger_safe'):
                record.__dict__.pop(key, None)
        return True


# Captured before any patching: the patched method must call the original, not
# itself, or dispatch would recurse forever.
_ORIGINAL_CALL_HANDLERS = logging.Logger.callHandlers


def _sanitising_call_handlers(self, record):
    """Rewrite the record once, just before it reaches ANY handler.

    A logger-level filter is not enough: Python applies `Logger.filter` only to
    the logger the call was made on, not to ancestors, so a record from
    `app.api` never passes through a filter placed on `root`. A handler-level
    filter also fails for handlers added later. Overriding dispatch is the only
    place that covers both, including the DB handler attached during lifespan.
    """
    PolicyFilter().filter(record)
    _ORIGINAL_CALL_HANDLERS(self, record)


class SafeLogger(logging.Logger):
    callHandlers = _sanitising_call_handlers


class SafeFormatter(logging.Formatter):
    """One line, fixed fields, no exception text."""

    def format(self, record):
        return '%s level=%s logger=%s route=%s' % (
            getattr(record, 'event', UNKNOWN_EVENT),
            record.levelname,
            getattr(record, 'logger_safe', 'other'),
            getattr(record, 'route', PLACEHOLDER))


def _replace_handlers():
    """Drop every existing handler, including ones added by uvicorn's config.

    Replacing the formatter is not enough: a handler installed earlier keeps its
    own formatter, and `lastResort` would print the raw record to stderr.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(SafeFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Every logger, present or future, sanitises on dispatch.
    logging.setLoggerClass(SafeLogger)
    logging.Logger.callHandlers = _sanitising_call_handlers
    root.callHandlers = _sanitising_call_handlers.__get__(root, type(root))
    logging.lastResort = None
    logging.raiseExceptions = False
    for name in list(logging.Logger.manager.loggerDict):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
        logger.callHandlers = _sanitising_call_handlers.__get__(logger, type(logger))


def _install_exception_hooks():
    def excepthook(exc_type, exc_value, tb):
        # Never format the exception: its message may contain the request.
        _emit(UNHANDLED, PLACEHOLDER, logging.ERROR)

    def unraisablehook(unraisable):
        _emit(UNHANDLED, PLACEHOLDER, logging.ERROR)

    sys.excepthook = excepthook
    sys.unraisablehook = unraisablehook

    def showwarning(message, category, filename, lineno, file=None, line=None):
        _emit(BACKGROUND, PLACEHOLDER, logging.WARNING)

    warnings.showwarning = showwarning


def _emit(event, route, level):
    logging.getLogger('app.isolation').log(level, '', extra={
        'event': event, 'route': route})


def install():
    """Install the whole chain. Idempotent; safe to call before app import."""
    _replace_handlers()
    _install_exception_hooks()
    logging.captureWarnings(True)
    return True


def safe_extra(event, route=PLACEHOLDER):
    """The only supported way for application code to add fields."""
    if event not in EVENTS:
        event = UNKNOWN_EVENT
    if route not in ROUTES:
        route = PLACEHOLDER
    return {'event': event, 'route': route}
