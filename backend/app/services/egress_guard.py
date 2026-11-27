"""Scoped request guards for model/embedding transports; no domain authority."""
import asyncio
import logging
from contextvars import ContextVar
from contextlib import contextmanager
from weakref import WeakKeyDictionary

_delivery_guard = ContextVar('ordinary_model_delivery_guard', default=None)
_delivery_client_locks = WeakKeyDictionary()
_sensitive_sdk_logging = ContextVar('sensitive_sdk_logging', default=False)


class _GuardedSDKLogFilter(logging.Filter):
    def filter(self, record):
        # SDK DEBUG records contain request JSON and exception input. Suppress
        # only this request's guarded SDK internals, leaving normal logs intact.
        return _delivery_guard.get() is None and not _sensitive_sdk_logging.get()


for _sdk_logger_name in ('openai._base_client', 'anthropic._base_client'):
    logging.getLogger(_sdk_logger_name).addFilter(_GuardedSDKLogFilter())


@contextmanager
def suppress_sdk_payload_logs():
    """Logging-only marker; it grants or changes no delivery authority."""
    token = _sensitive_sdk_logging.set(True)
    try:
        yield
    finally:
        _sensitive_sdk_logging.reset(token)


class GuardedProviderError(RuntimeError):
    """Safe terminal diagnostics; never retain the provider response or input."""
    def __init__(self, error_type, status_code=None):
        self.error_type = error_type
        self.status_code = status_code
        suffix = f' (status {status_code})' if status_code is not None else ''
        super().__init__(f'Provider request failed: {error_type}{suffix}')


def safe_provider_error(error):
    if isinstance(error, GuardedProviderError):
        return error
    if isinstance(error, PermissionError):
        return PermissionError('D4_DELIVERY_UNAVAILABLE')
    status = getattr(error, 'status_code', None)
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    return GuardedProviderError(type(error).__name__, status)


async def before_physical_request():
    guard = _delivery_guard.get()
    if guard is not None:
        try:
            await guard()
        except Exception:
            raise PermissionError('D4_DELIVERY_UNAVAILABLE') from None


async def with_delivery_guard(guard, operation):
    """Recheck a server-owned input set, including provider failure paths."""
    previous = _delivery_guard.get()
    async def composed():
        if previous is not None:
            await previous()
        await guard()
    active = composed if previous is not None and previous is not guard else guard
    token = _delivery_guard.set(active)
    try:
        await active()
        try:
            result = await operation()
        except Exception as error:
            try:
                await active()
            except Exception:
                raise PermissionError('D4_DELIVERY_UNAVAILABLE') from None
            raise safe_provider_error(error) from None
        try:
            await active()
        except Exception:
            raise PermissionError('D4_DELIVERY_UNAVAILABLE') from None
        return result
    finally:
        _delivery_guard.reset(token)


async def _run_guarded_operation(operation):
    await before_physical_request()
    try:
        result = await operation()
    except Exception as error:
        if _delivery_guard.get() is not None:
            try:
                await before_physical_request()
            except Exception:
                raise PermissionError('D4_DELIVERY_UNAVAILABLE') from None
            raise safe_provider_error(error) from None
        raise
    if _delivery_guard.get() is not None:
        try:
            await before_physical_request()
        except Exception:
            raise PermissionError('D4_DELIVERY_UNAVAILABLE') from None
    return result


async def run_sdk_operation(client, operation):
    guarded = _delivery_guard.get() is not None
    request_client = client.with_options(max_retries=0) if guarded else client
    http_client = getattr(request_client, '_client', None)
    if http_client is None:
        if guarded:
            raise PermissionError('D4_DELIVERY_UNAVAILABLE')
        return await operation(request_client)
    return await run_http_operation(http_client, lambda: operation(request_client))


async def run_http_operation(client, operation):
    guarded = _delivery_guard.get() is not None
    lock = _delivery_client_locks.setdefault(client, asyncio.Lock())
    async with lock:
        prior_redirects = client.follow_redirects
        if guarded:
            client.follow_redirects = False
        try:
            return await _run_guarded_operation(operation)
        finally:
            if guarded:
                client.follow_redirects = prior_redirects

