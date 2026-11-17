"""Behavioural tests for one-shot delivery and bounded output.

No container, no pipe: a fake channel that counts writes and a fake chunk
stream. What is pinned is that the configuration leaves once, and that receiver
output can never accumulate.
"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    '_i7_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
c = h.load('controller')

SECRET = b'{"secret":"sk-live-SENTINEL","tenant_slug":"t"}'


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


class Channel:
    def __init__(self, *, partial=None, fail_after=None):
        self.received = []
        self.closed = False
        self.delivered = False
        self.partial = partial
        self.fail_after = fail_after
        self.writes = 0

    def write(self, data):
        self.writes += 1
        if self.fail_after is not None and self.writes > self.fail_after:
            return 0
        take = self.partial or len(data)
        take = min(take, len(data))
        self.received.append(bytes(data[:take]))
        return take

    def close(self):
        self.closed = True


def test_the_configuration_is_written_once_and_then_closed():
    channel = Channel()
    result = c.deliver_once(channel, SECRET)
    assert (result.result, result.reason) == (c.DELIVERED, 'delivered')
    assert b''.join(channel.received) == SECRET
    assert channel.closed is True


def test_a_second_delivery_is_refused():
    channel = Channel()
    assert c.deliver_once(channel, SECRET).result == c.DELIVERED
    second = c.deliver_once(channel, SECRET)
    assert (second.result, second.reason) == (c.REFUSED, 'already_delivered')
    assert b''.join(channel.received) == SECRET      # nothing more was written


def test_a_partial_write_is_continued_but_still_one_delivery():
    channel = Channel(partial=7)
    result = c.deliver_once(channel, SECRET)
    assert result.result == c.DELIVERED
    assert b''.join(channel.received) == SECRET
    assert channel.writes > 1


def test_a_stalled_write_is_refused_and_the_channel_still_closes():
    # First write takes a few bytes, every later one returns 0: a real stall.
    channel = Channel(partial=5, fail_after=1)
    result = c.deliver_once(channel, SECRET)
    assert (result.result, result.reason) == (c.REFUSED, 'write_failed')
    assert channel.closed is True


@pytest.mark.parametrize('payload,reason', [
    (b'', 'payload_empty'),
    ('text', 'payload_invalid'),
    (b'x' * (c.CONFIG_LIMIT + 1), 'payload_too_large'),
])
def test_unusable_payloads_are_refused_without_writing(payload, reason):
    channel = Channel()
    result = c.deliver_once(channel, payload)
    assert (result.result, result.reason) == (c.REFUSED, reason)
    assert channel.received == []


def test_output_is_counted_not_stored():
    budget = c.OutputBudget()
    chunks = [b'x' * c.CHUNK] * 100
    overflow = c.read_bounded(chunks, budget)
    assert overflow is not None
    assert budget.exceeded is True
    assert budget.used > c.OUTPUT_LIMIT
    # The budget holds a count only; it never retains the bytes.
    assert set(vars(budget)) == {'limit', 'used'}


def test_output_within_budget_is_not_flagged():
    budget = c.OutputBudget()
    assert c.read_bounded([b'y' * 1024] * 4, budget) is None
    assert budget.exceeded is False


def test_the_overflow_is_reported_at_the_first_offending_chunk():
    budget = c.OutputBudget(limit=10)
    overflow = c.read_bounded([b'a' * 4, b'b' * 4, b'c' * 4], budget)
    assert len(overflow) == 4
    assert budget.used == 12


def test_results_are_fixed_and_validated():
    assert c.DeliveryResult(c.DELIVERED, 'delivered') == c.DeliveryResult(c.DELIVERED, 'delivered')
    for bad in ('completed', 'ok', ''):
        with pytest.raises(ValueError):
            c.DeliveryResult(bad, 'x')
    with pytest.raises(ValueError):
        c.DeliveryResult(c.DELIVERED, '')
