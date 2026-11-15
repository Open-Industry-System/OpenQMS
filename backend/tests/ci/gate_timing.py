"""Pytest-only timers, loaded lazily so receipt utilities remain stdlib-only."""
import time

import pytest


class GateTiming:
    def __init__(self, state):
        self.state = state

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection(self, session):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.state['collection_seconds'] = time.perf_counter() - started

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtestloop(self, session):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.state['execution_seconds'] = time.perf_counter() - started
