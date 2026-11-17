"""One-shot configuration delivery and bounded output for a receiver session.

Two rules drive this module, and both are about what the controller never does:

* it writes the configuration exactly once, to an already-attached stdin, and
  then closes it. There is no retry, no replay and no second channel;
* it never holds receiver output. stdout and stderr are read in small chunks,
  counted, and dropped. A combined budget of 4 KiB is enforced on the count, not
  on a buffer, so an unlimited stream cannot grow the controller's memory.

The result is only ever one of the fixed infrastructure states; the receiver's
own words never become the controller's conclusion.
"""
from dataclasses import dataclass

OUTPUT_LIMIT = 4096          # design 8.3: stdout+stderr combined
CHUNK = 512                  # read size; never accumulated
CONFIG_LIMIT = 64 * 1024     # design: private configuration upper bound

DELIVERED = 'delivered'
REFUSED = 'refused'
OVERFLOW = 'overflow'
CLOSED = 'closed'


def _require(condition, message='controller_invalid'):
    if not condition:
        raise ValueError(message)


@dataclass
class OutputBudget:
    """Counts bytes read from the receiver; stores none of them."""
    limit: int = OUTPUT_LIMIT
    used: int = 0

    def __post_init__(self):
        _require(type(self.limit) is int and self.limit > 0)

    def consume(self, chunk):
        """Count one chunk. Returns True while still within budget."""
        _require(isinstance(chunk, (bytes, bytearray, memoryview)), 'chunk_invalid')
        size = len(chunk)
        self.used += size
        return self.used <= self.limit

    @property
    def exceeded(self):
        return self.used > self.limit


class DeliveryResult:
    """Fixed outcomes; no receiver text is carried."""

    def __init__(self, result, reason):
        _require(result in (DELIVERED, REFUSED, OVERFLOW, CLOSED), 'result_invalid')
        _require(type(reason) is str and reason != '')
        self.result = result
        self.reason = reason

    def __eq__(self, other):
        return (type(other) is DeliveryResult and self.result == other.result
                and self.reason == other.reason)

    def __repr__(self):
        return 'DeliveryResult(%r, %r)' % (self.result, self.reason)


class Channel:
    """What the controller needs from an attached stdin.

    `write` must accept the whole buffer or report how much it took; a partial
    write is legitimate and is continued, but the configuration is still written
    only once.
    """

    def write(self, data):                    # pragma: no cover - protocol
        raise NotImplementedError

    def close(self):                          # pragma: no cover - protocol
        raise NotImplementedError


def deliver_once(channel, payload):
    """Write the six-field configuration exactly once, then close the channel."""
    _require(callable(getattr(channel, 'write', None)), 'channel_invalid')
    _require(callable(getattr(channel, 'close', None)), 'channel_invalid')
    if type(payload) is not bytes:
        return DeliveryResult(REFUSED, 'payload_invalid')
    if not payload:
        return DeliveryResult(REFUSED, 'payload_empty')
    if len(payload) > CONFIG_LIMIT:
        return DeliveryResult(REFUSED, 'payload_too_large')
    if getattr(channel, 'delivered', False):
        # A second delivery would be a second secret write.
        return DeliveryResult(REFUSED, 'already_delivered')
    written = 0
    try:
        while written < len(payload):
            count = channel.write(payload[written:])
            if type(count) is not int or count <= 0:
                return DeliveryResult(REFUSED, 'write_failed')
            written += count
    finally:
        # Close in every case: a half-written configuration must not stay open
        # for a later attempt to finish.
        try:
            channel.close()
        except Exception:
            pass
        channel.delivered = True
    return DeliveryResult(DELIVERED, 'delivered')


def read_bounded(chunks, budget):
    """Drain an iterable of output chunks without retaining any of them.

    Returns the first chunk that pushes the receiver past its budget, or None.
    The count is what is enforced; the bytes are already gone.
    """
    _require(type(budget) is OutputBudget, 'budget_invalid')
    for chunk in chunks:
        if not budget.consume(chunk):
            return chunk
    return None
