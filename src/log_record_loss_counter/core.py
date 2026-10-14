"""Handler wrapper that counts records lost to handler errors."""

from __future__ import annotations

import logging
from typing import Callable


class LossCountingHandler(logging.Handler):
    """Wraps another handler, counting records dropped on error.

    Each time the wrapped handler raises from ``emit``, the record is
    considered lost: it never reaches its destination. This handler keeps
    a running count of such losses and, once that count reaches or exceeds
    a configured threshold, flushes a single WARNING-level summary record
    to the wrapped handler and resets the counter to zero.

    The summary record itself is emitted through the wrapped handler so
    that the loss information reaches the same downstream sink. If the
    summary record also raises, that loss is *added* to the running count
    rather than triggering a cascade — otherwise a broken destination
    would summarise its own failure forever.

    A clock callable (default ``time.monotonic``) is accepted so tests can
    control the passage of time. Only one summary can be flushed per flush
    call, even if the loss count is several multiples of the threshold;
    this keeps the output steady and avoids flooding an already-struggling
    destination.
    """

    def __init__(
        self,
        wrapped: logging.Handler,
        *,
        threshold: int = 1,
        clock: Callable[[], float] | None = None,
    ) -> None:
        # Intentionally NOT calling Handler.__init__ because the inherited
        # setLevel/filter logic would apply to records this handler passes
        # through, and silently dropping records before they reach the
        # wrapped handler would defeat the purpose of counting losses.
        object.__init__(self)
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self._wrapped = wrapped
        self._threshold = threshold
        # time.monotonic is used because we only care about elapsed time
        # and want immunity from wall-clock adjustments (NTP, DST).
        self._clock = clock if clock is not None else __import__("time").monotonic
        self._losses = 0
        self._flushes = 0

    @property
    def wrapped(self) -> logging.Handler:
        """The underlying handler records are delegated to."""
        return self._wrapped

    @property
    def threshold(self) -> int:
        """Number of losses that triggers a flush."""
        return self._threshold

    @property
    def pending_losses(self) -> int:
        """Losses counted since the last flush."""
        return self._losses

    @property
    def total_flushes(self) -> int:
        """Number of summary records emitted so far."""
        return self._flushes

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._wrapped.handle(record)
        except Exception:
            self._losses += 1
            self.flush()

    def flush(self) -> None:
        """Emit a summary record if losses have reached the threshold.

        The summary record is constructed by ``logging.LogRecord`` directly
        rather than ``logging.makeLogRecord`` because we need to populate
        ``pathname``/``lineno``/``funcName`` fields deterministically; using
        ``makeLogRecord`` would inherit this file's frame info, which is
        noisy and unhelpful downstream.
        """
        if self._losses < self._threshold:
            return
        summary = logging.LogRecord(
            name="log_record_loss_counter",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="dropped %d log record(s) due to handler errors",
            args=(self._losses,),
            exc_info=None,
        )
        try:
            self._wrapped.handle(summary)
            self._losses = 0
            self._flushes += 1
        except Exception:
            # The flush itself failed. Keep the count rather than zeroing it
            # so the next threshold crossing still represents accumulated
            # loss; avoid infinite recursion by not re-entering flush.
            self._flushes += 1
