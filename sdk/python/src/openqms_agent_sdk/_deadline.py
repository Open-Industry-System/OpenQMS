"""One absolute monotonic budget, shared by all phases of an operation."""
import time

from .errors import RequestTimeout


class Deadline:
    def __init__(self, timeout, operation, *, clock=time.monotonic):
        self.operation = operation
        self._clock = clock
        self._end = clock() + timeout

    def remaining(self):
        remaining = self._end - self._clock()
        if remaining <= 0:
            raise RequestTimeout(self.operation, kind='deadline')
        return remaining

    def check(self):
        self.remaining()
