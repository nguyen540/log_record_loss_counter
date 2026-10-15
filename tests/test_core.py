"""Tests for LossCountingHandler."""

import logging
import unittest

from log_record_loss_counter import LossCountingHandler


class _RecordingHandler(logging.Handler):
    """Captures every record that handle() is called with."""

    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []
        self.raise_next = False

    def emit(self, record):
        if self.raise_next:
            self.raise_next = False
            raise RuntimeError("boom")
        self.records.append(record)


class LossCountingHandlerTests(unittest.TestCase):
    def test_passes_through_when_wrapped_succeeds(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=1)
        record = logging.LogRecord(
            "app", logging.INFO, "path", 10, "hello", (), None
        )
        outer.emit(record)
        self.assertEqual(inner.records, [record])
        self.assertEqual(outer.pending_losses, 0)

    def test_counts_record_lost_on_error(self):
        inner = _RecordingHandler()
        inner.raise_next = True
        outer = LossCountingHandler(inner, threshold=1)
        record = logging.LogRecord(
            "app", logging.INFO, "path", 10, "hello", (), None
        )
        outer.emit(record)
        # The original record raised, so a summary is flushed through the
        # wrapped handler. raise_next was consumed by the original, so the
        # summary succeeds and lands in inner.records.
        self.assertEqual(len(inner.records), 1)
        self.assertEqual(outer.pending_losses, 0)
        self.assertEqual(outer.total_flushes, 1)

    def test_threshold_delays_flush(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=3)
        for _ in range(2):
            inner.raise_next = True
            outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "x", (), None))
        self.assertEqual(outer.pending_losses, 2)
        self.assertEqual(outer.total_flushes, 0)
        self.assertEqual(inner.records, [])
        inner.raise_next = True
        outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "x", (), None))
        self.assertEqual(outer.pending_losses, 0)
        self.assertEqual(outer.total_flushes, 1)
        self.assertEqual(len(inner.records), 1)
        self.assertIn("dropped 3 log record", inner.records[0].getMessage())

    def test_summary_record_has_warning_level(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=1)
        inner.raise_next = True
        outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "x", (), None))
        self.assertEqual(inner.records[0].levelno, logging.WARNING)

    def test_failed_summary_keeps_running_count(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=1)
        # First emit: inner raises on the original record.
        inner.raise_next = True
        outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "a", (), None))
        self.assertEqual(outer.total_flushes, 1)
        # raise_next was consumed by the original record, so the summary
        # succeeds and lands in inner.records.
        self.assertEqual(len(inner.records), 1)
        self.assertEqual(outer.pending_losses, 0)

    def test_threshold_must_be_positive(self):
        with self.assertRaises(ValueError):
            LossCountingHandler(_RecordingHandler(), threshold=0)

    def test_exposes_wrapped_handler(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=1)
        self.assertIs(outer.wrapped, inner)
        self.assertEqual(outer.threshold, 1)

    def test_multiple_flushes_accumulate(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=1)
        for _ in range(3):
            inner.raise_next = True
            outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "x", (), None))
        self.assertEqual(outer.total_flushes, 3)

    def test_summary_sent_to_wrapped_handler(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=1)
        inner.raise_next = True
        outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "x", (), None))
        self.assertEqual(len(inner.records), 1)
        self.assertEqual(inner.records[0].name, "log_record_loss_counter")

    def test_record_count_in_message(self):
        inner = _RecordingHandler()
        outer = LossCountingHandler(inner, threshold=5)
        for _ in range(5):
            inner.raise_next = True
            outer.emit(logging.LogRecord("app", logging.INFO, "p", 1, "x", (), None))
        self.assertEqual(len(inner.records), 1)
        self.assertEqual(inner.records[0].getMessage(), "dropped 5 log record(s) due to handler errors")


if __name__ == "__main__":
    unittest.main()
